"""Local dashboard: one browser worker, token-protected API, safe persisted history."""

import json
import re
import secrets
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Literal, cast
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import Field

from .demo import serve, validate_demo_url
from .discovery import discover
from .gemini import GeminiDecider
from .provider import Budget
from .replay import replay
from .schema import Capability, Contract, Inputs, Result
from .surface import SCENARIOS


def member_from_goal(goal: str) -> str | None:
    """Recognize one explicitly identified member; leave ambiguity to the user."""
    numbers = set(re.findall(r"(?<![\w.])[0-9]{5}(?![\w.]|[.,][0-9])", goal))
    matches = set(
        re.findall(
            r"\b(?:member|customer)(?:\s+(?:id|number|no\.?))?\s*[:#-]?\s*([0-9]{5})(?![\w.]|[.,][0-9])",
            goal,
            re.IGNORECASE,
        )
    )
    matches.update(
        re.findall(
            r"(?<![\w.])([0-9]{5})['’]s\s+(?:savings\s+)?balance\b",
            goal,
            re.IGNORECASE,
        )
    )
    return next(iter(matches)) if len(matches) == 1 and matches == numbers else None


def replay_fields(capability: Capability) -> list[dict[str, Any]]:
    """Derive form fields from parameterized steps, never from example values."""
    properties = Inputs.model_json_schema()["properties"]
    fields: dict[str, dict[str, Any]] = {}
    for step in capability.steps:
        if step.parameter and step.parameter not in fields:
            definition = properties[step.parameter]
            fields[step.parameter] = {
                "key": step.parameter,
                "label": step.name,
                "type": "text",
                "required": True,
                "pattern": definition.get("pattern", ""),
            }
    return list(fields.values())


class RunRequest(Contract):
    mode: Literal["replay", "discover"]
    member_id: str | None = Field(default=None, pattern=r"^[0-9]{5}$")
    workflow: str = ""
    goal: str = Field(default="Read the member savings balance", min_length=1, max_length=500)
    scenario: str = "normal"
    live: bool = False
    target_url: str = Field(default="", max_length=2048)
    inputs: dict[str, str] = Field(default_factory=dict)


class EventLog(list[dict[str, object]]):
    def __init__(self, manager: "Dashboard", run: dict[str, Any], path: Path):
        super().__init__()
        self.manager, self.run, self.path = manager, run, path

    def append(self, event: dict[str, object]) -> None:
        with self.manager.lock:
            super().append(event)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event) + "\n")
            self.run["events"] = list(self)
            if event["event"] == "intervention":
                self.run["status"] = "needs_review"
                self.run["pause_pending"] = False
            elif event["event"] == "resumed":
                self.run["status"] = "running"


class Dashboard:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = self.root / "runs" / "dashboard"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.active: str | None = None
        self.demo_url = ""
        self.pause_request = Event()
        self.runs: dict[str, dict[str, Any]] = {}
        self.pending: dict[str, RunRequest] = {}
        self.drafts: dict[str, Capability] = {}
        for path in sorted(self.directory.glob("*/summary.json")):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
                run["events"] = [
                    json.loads(line)
                    for line in (path.parent / "events.jsonl").read_text().splitlines()
                ]
                run["outputs_available"] = False
                self.runs[path.parent.name] = run
            except (OSError, ValueError):
                continue

    def workflows(self) -> dict[str, Capability]:
        found: dict[str, Capability] = {}
        paths = [
            *self.root.glob("artifacts/*.json"),
            *self.root.glob("evidence/*capability*.json"),
            *self.directory.glob("*/capability.json"),
        ]
        for path in paths:
            try:
                found[path.relative_to(self.root).as_posix()] = Capability.model_validate_json(
                    path.read_text()
                )
            except (ValueError, OSError):
                continue
        return found

    def snapshot(self) -> dict[str, Any]:
        workflows = []
        try:
            names = json.loads((self.directory / "workflow-names.json").read_text(encoding="utf-8"))
            if not isinstance(names, dict):
                names = {}
        except (OSError, ValueError):
            names = {}
        items = list(self.workflows().items())
        items.sort(key=lambda item: (self.root / item[0]).stat().st_mtime)
        for number, (key, value) in enumerate(items, 1):
            path = self.root / key
            run_id = path.parent.name if key.startswith("runs/dashboard/") else None
            with self.lock:
                created = self.runs.get(run_id or "", {}).get("created")
            if not created:
                created = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
            fixes = [rule.trigger for rule in value.recoveries]
            description = "Standard lookup"
            if fixes:
                description = " + ".join(
                    {"operator_review": "Review recovery", "session_expired": "Session recovery"}[
                        fix
                    ]
                    for fix in fixes
                )
            source = "Your workflow" if run_id else "Example"
            workflows.append(
                {
                    "id": key,
                    "name": names.get(key, f"Savings lookup {number:02d}"),
                    "description": description,
                    "source": source,
                    "created": created,
                    "provenance": value.provenance,
                    "steps": [step.model_dump() for step in value.steps],
                    "recoveries": [rule.model_dump() for rule in value.recoveries],
                    "inputs": replay_fields(value),
                }
            )
        workflows.sort(
            key=lambda item: (item["source"] == "Your workflow", item["created"]), reverse=True
        )
        with self.lock:
            return deepcopy(
                {
                    "active": self.active,
                    "demo_url": self.demo_url,
                    "workflows": workflows,
                    "runs": sorted(
                        self.runs.values(), key=lambda run: run["created"], reverse=True
                    ),
                }
            )

    def start(self, request: RunRequest) -> str:
        if request.scenario not in SCENARIOS:
            raise ValueError("Choose a supported scenario.")
        capability = self.workflows().get(request.workflow)
        if request.mode == "replay" and capability is None:
            raise ValueError("Choose a saved workflow.")
        if request.mode == "replay" and request.inputs:
            assert capability is not None
            expected = {field["key"] for field in replay_fields(capability)}
            if set(request.inputs) != expected:
                raise ValueError("Inputs do not match the selected workflow.")
            request.member_id = Inputs.model_validate(request.inputs).member_id
        if request.mode == "replay" and request.member_id is None:
            raise ValueError("Provide the workflow inputs.")
        if request.mode == "discover" and not request.live:
            raise ValueError("Confirm API quota use before discovery.")
        if request.target_url:
            request.target_url = validate_demo_url(request.target_url)
        goal_first = request.mode == "discover" and request.member_id is None
        if goal_first:
            request.member_id = member_from_goal(request.goal)
        with self.lock:
            if self.active:
                raise ValueError("A run is already active. Complete its browser review first.")
            run_id = uuid4().hex
            folder = self.directory / run_id
            folder.mkdir()
            run = {
                "id": run_id,
                "mode": request.mode,
                "status": "running",
                "events": [],
                "created": datetime.now(UTC).isoformat(),
                "scenario": request.scenario,
                "workflow": request.workflow if request.mode == "replay" else "",
                "review_before_save": goal_first,
            }
            self.runs[run_id] = run
            self.pause_request.clear()
            self.active = run_id
            if request.member_id is None:
                run["status"] = "needs_input"
                run["question"] = "Which sample member should I use to learn this savings lookup?"
                self.pending[run_id] = request
                return run_id
        Thread(target=self.execute, args=(request, capability, run, folder), daemon=True).start()
        return run_id

    def answer(self, run_id: str, member_id: str) -> None:
        inputs = Inputs(member_id=member_id)
        with self.lock:
            if self.active != run_id or run_id not in self.pending:
                raise ValueError("No input is pending.")
            request = self.pending.pop(run_id)
            request.member_id = inputs.member_id
            run = self.runs[run_id]
            run.pop("question", None)
            run["status"] = "running"
            run["review_before_save"] = True
        Thread(
            target=self.execute, args=(request, None, run, self.directory / run_id), daemon=True
        ).start()

    def rename(self, workflow: str, name: str) -> None:
        name = name.strip()
        if (
            workflow not in self.workflows()
            or not 1 <= len(name) <= 80
            or any(ord(c) < 32 for c in name)
        ):
            raise ValueError("Choose a saved workflow and a name of 1 to 80 characters")
        with self.lock:
            path = self.directory / "workflow-names.json"
            names = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            names[workflow] = name
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(names, indent=2), encoding="utf-8")
            temporary.replace(path)

    def review(self, run_id: str, save: bool) -> None:
        with self.lock:
            if run_id not in self.drafts:
                raise ValueError("No draft is pending.")
            capability = self.drafts[run_id]
            if save:
                (self.directory / run_id / "capability.json").write_text(
                    capability.model_dump_json(indent=2), encoding="utf-8"
                )
            del self.drafts[run_id]
            self.runs[run_id].pop("draft", None)
            self.runs[run_id]["review_outcome"] = "saved" if save else "discarded"

    def cancel_input(self, run_id: str) -> None:
        with self.lock:
            if self.active != run_id or run_id not in self.pending:
                raise ValueError("No input is pending.")
            del self.pending[run_id]
            self.runs[run_id].update(status="cancelled")
            self.runs[run_id].pop("question", None)
            self.active = None

    def request_pause(self, run_id: str) -> None:
        with self.lock:
            if self.active != run_id or self.runs[run_id]["status"] != "running":
                raise ValueError("Run is not available for takeover")
            self.pause_request.set()
            self.runs[run_id]["pause_pending"] = True

    def execute(
        self, request: RunRequest, capability: Capability | None, run: dict[str, Any], folder: Path
    ) -> None:
        events = EventLog(self, run, folder / "events.jsonl")
        result = Result(status="failure", code="dashboard_execution_failed").with_details()
        try:
            assert request.member_id is not None
            inputs = Inputs(member_id=request.member_id)
            target = nullcontext(request.target_url) if request.target_url else serve()
            with target as url:
                if request.mode == "discover":
                    decider = GeminiDecider(
                        "gemini-2.5-flash",
                        Budget(self.root / ".local" / "budget.json"),
                        self.root / ".env",
                    )
                    decider.events = events
                    result, created = discover(
                        request.goal,
                        inputs,
                        url,
                        decider,
                        scenario=request.scenario,
                        headed=True,
                        events=events,
                        failure_screenshot=folder / "failure.png",
                        pause_request=self.pause_request,
                        action_delay=2.0,
                    )
                    if created and run.get("review_before_save"):
                        with self.lock:
                            self.drafts[run["id"]] = created
                            run["draft"] = {
                                "inputs": replay_fields(created),
                                "output": created.output_type,
                                "steps": [step.model_dump() for step in created.steps],
                                "recoveries": [rule.model_dump() for rule in created.recoveries],
                            }
                    elif created:
                        (folder / "capability.json").write_text(
                            created.model_dump_json(indent=2), encoding="utf-8"
                        )
                else:
                    assert capability is not None
                    result = replay(
                        capability,
                        inputs,
                        url,
                        scenario=request.scenario,
                        headed=True,
                        events=events,
                        failure_screenshot=folder / "failure.png",
                        pause_request=self.pause_request,
                        action_delay=2.0,
                    )
                    if result.status == "success" and any(
                        e["event"] == "capability_updated" for e in events
                    ):
                        (folder / "capability.json").write_text(
                            capability.model_dump_json(indent=2), encoding="utf-8"
                        )
        except Exception:  # noqa: BLE001 - worker boundary must sanitize unexpected failures
            # Raw errors may contain goal/input/provider data; never send them to the UI.
            result = Result(
                status="failure",
                code="dashboard_execution_failed",
                expected="Configured key, browser and writable local storage",
                observed="Run could not complete; check local setup",
            ).with_details()
        finally:
            safe = result.with_details().model_dump(exclude={"outputs"})
            try:
                events.append({"event": "result", **safe})
                with self.lock:
                    summary = {**run, "status": result.status, "result": safe}
                    summary.pop("events", None)
                    summary.pop("draft", None)
                    (folder / "summary.json").write_text(
                        json.dumps(summary, indent=2), encoding="utf-8"
                    )
            finally:
                with self.lock:
                    run.update(
                        status=result.status, result=result.model_dump(), outputs_available=True
                    )
                    self.active = None


def make_server(root: Path, port: int = 8766) -> ThreadingHTTPServer:
    manager = Dashboard(root)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def allowed(self, api: bool = True) -> bool:
            host = f"127.0.0.1:{cast(ThreadingHTTPServer, self.server).server_port}"
            return (
                self.headers.get("Host") == host
                and self.headers.get("Origin", f"http://{host}") == f"http://{host}"
                and (
                    not api
                    or secrets.compare_digest(self.headers.get("X-Dashboard-Token", ""), token)
                )
            )

        def send_body(
            self, status: int, body: bytes, content_type: str = "application/json"
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' blob:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if not self.allowed(api=path != "/"):
                self.send_body(403, b'{"error":"Local dashboard access required."}')
                return
            if path == "/":
                page = (
                    files("interface_automation")
                    .joinpath("dashboard.html")
                    .read_text(encoding="utf-8")
                )
                self.send_body(
                    200, page.replace("__TOKEN__", token).encode(), "text/html; charset=utf-8"
                )
            elif path == "/api/state":
                self.send_body(200, json.dumps(manager.snapshot()).encode())
            elif path.startswith("/api/screenshot/"):
                run_id = path.rsplit("/", 1)[-1]
                if run_id in manager.runs and (manager.directory / run_id / "failure.png").exists():
                    self.send_body(
                        200, (manager.directory / run_id / "failure.png").read_bytes(), "image/png"
                    )
                else:
                    self.send_body(404, b"{}")
            else:
                self.send_body(404, b"{}")

        def do_POST(self) -> None:
            if not self.allowed() or self.path not in {
                "/api/run",
                "/api/pause",
                "/api/answer",
                "/api/review",
                "/api/cancel-input",
                "/api/rename",
            }:
                self.send_body(403, b'{"error":"Request rejected."}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("Invalid request size.")
                body = self.rfile.read(length)
                if self.path == "/api/rename":
                    data = json.loads(body)
                    if (
                        not isinstance(data, dict)
                        or not isinstance(data.get("workflow"), str)
                        or not isinstance(data.get("name"), str)
                    ):
                        raise ValueError("Invalid workflow name")
                    manager.rename(data["workflow"], data["name"])
                    self.send_body(200, b"{}")
                    return
                if self.path in {"/api/answer", "/api/review", "/api/cancel-input"}:
                    data = json.loads(body)
                    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
                        raise ValueError("Invalid run identifier")
                    if self.path == "/api/answer":
                        if not isinstance(data.get("member_id"), str):
                            raise ValueError("Provide a sample member number")
                        manager.answer(data["id"], data["member_id"])
                    elif self.path == "/api/cancel-input":
                        manager.cancel_input(data["id"])
                    else:
                        if not isinstance(data.get("save"), bool):
                            raise ValueError("Choose save or discard")
                        manager.review(data["id"], data["save"])
                    self.send_body(200, b"{}")
                    return
                if self.path == "/api/pause":
                    data = json.loads(body)
                    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
                        raise ValueError("Invalid run identifier")
                    manager.request_pause(data["id"])
                    self.send_body(202, b'{"status":"pause_requested"}')
                    return
                request = RunRequest.model_validate_json(body)
                run_id = manager.start(request)
                self.send_body(202, json.dumps({"id": run_id}).encode())
            except ValueError:
                self.send_body(
                    400,
                    b'{"error":"Check the demo URL is running the bundled demo, your inputs, API consent, workflow selection, and whether a run is already active."}',
                )

    demo_context = serve()

    class DashboardServer(ThreadingHTTPServer):
        def server_close(self) -> None:
            super().server_close()
            demo_context.__exit__(None, None, None)

    server = DashboardServer(("127.0.0.1", port), Handler)
    manager.demo_url = demo_context.__enter__()
    return server
