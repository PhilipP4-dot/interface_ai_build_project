"""Local replay and explicitly enabled live discovery."""

import argparse
import json
from pathlib import Path
from threading import Event

from pydantic import ValidationError

from .demo import serve
from .policy import Policy
from .replay import replay
from .schema import Capability, Inputs, Result
from .surface import SCENARIOS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    dashboard = commands.add_parser("dashboard", help="Open the local workflow dashboard")
    dashboard.add_argument("--port", type=int, default=8766)
    demo = commands.add_parser("demo", help="Serve synthetic UI on loopback")
    demo.add_argument("--port", type=int, default=8765)
    run = commands.add_parser("replay", help="Replay fixture against a temporary local demo")
    run.add_argument("--artifact", type=Path, default=Path("artifacts/savings_balance.json"))
    run.add_argument("--member-id", required=True)
    run.add_argument(
        "--target",
        choices=["synthetic-bank"],
        default="synthetic-bank",
        help="Supported application entry point (local synthetic bank)",
    )
    run.add_argument("--headed", action="store_true")
    run.add_argument(
        "--updated-artifact",
        type=Path,
        help="Save a new workflow version with verified human fixes",
    )
    run.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="normal",
    )
    run.add_argument("--events", type=Path, help="Write sanitized action/handoff events")
    run.add_argument(
        "--policy", type=Path, help="JSON allowlist (defaults to built-in read-only policy)"
    )
    run.add_argument(
        "--failure-screenshot", type=Path, help="Masked screenshot on synthetic UI failure"
    )
    discovery = commands.add_parser("discover", help="Opt-in API discovery against synthetic UI")
    discovery.add_argument("--goal", required=True)
    discovery.add_argument(
        "--target",
        choices=["synthetic-bank"],
        default="synthetic-bank",
        help="Supported application entry point (local synthetic bank)",
    )
    discovery.add_argument("--member-id", required=True)
    discovery.add_argument(
        "--model",
        default="gemini-2.5-flash",
        choices=["gpt-5.4", "gemini-2.5-flash", "gemini-2.0-flash"],
    )
    discovery.add_argument("--live", action="store_true", help="Explicitly allow API quota use")
    discovery.add_argument("--headed", action="store_true")
    discovery.add_argument("--scenario", choices=SCENARIOS, default="normal")
    discovery.add_argument("--output", type=Path, required=True)
    discovery.add_argument("--events", type=Path, required=True)
    discovery.add_argument("--policy", type=Path, help="JSON allowlist")
    discovery.add_argument(
        "--failure-screenshot", type=Path, help="Masked synthetic UI failure screenshot"
    )
    args = parser.parse_args()
    if args.command == "dashboard":
        from .dashboard import make_server

        server = make_server(Path(__file__).resolve().parents[2], args.port)
        print(f"Workflow dashboard: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.command == "demo":
        with serve(args.port) as url:
            print(f"Synthetic demo: {url} (Ctrl+C to stop)", flush=True)
            try:
                Event().wait()
            except KeyboardInterrupt:
                pass
        return 0
    if args.command == "discover":
        return run_discovery(args)
    try:
        capability = Capability.model_validate_json(args.artifact.read_text(encoding="utf-8"))
        inputs = Inputs(member_id=args.member_id)
        policy = load_policy(args.policy)
    except (OSError, ValidationError):
        print(json.dumps({"status": "failure", "code": "invalid_artifact_or_input"}))
        return 2
    if args.events and args.events.exists():
        parser.error("Events path already exists; choose a new filename")
    if args.failure_screenshot and (
        args.failure_screenshot.exists() or args.failure_screenshot == args.events
    ):
        parser.error("Choose an unused, separate screenshot filename")
    if args.updated_artifact and args.updated_artifact.exists():
        parser.error("Choose an unused updated-artifact path")
    outputs = [
        path.resolve()
        for path in (args.events, args.failure_screenshot, args.updated_artifact)
        if path
    ]
    if len(outputs) != len(set(outputs)):
        parser.error("Output files must use separate paths")
    events: list[dict[str, object]] = []
    with serve() as url:
        result = replay(
            capability,
            inputs,
            url,
            args.scenario,
            args.headed,
            events=events,
            failure_screenshot=args.failure_screenshot,
            policy=policy,
        )
    if args.updated_artifact and result.status == "success":
        args.updated_artifact.parent.mkdir(parents=True, exist_ok=True)
        with args.updated_artifact.open("x", encoding="utf-8") as stream:
            stream.write(capability.model_dump_json(indent=2))
    if args.events:
        save_events(args.events, events, result)
    print(result.model_dump_json(indent=2))
    return 1 if result.status == "failure" else 0


def save_events(path: Path, events: list[dict[str, object]], result: Result) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        # Outputs belong to the caller, not the persisted diagnostic log.
        final = result.with_details().model_dump(exclude={"outputs"})
        for event in [*events, {"event": "result", **final}]:
            stream.write(json.dumps(event) + "\n")


def load_policy(path: Path | None) -> Policy:
    return Policy.model_validate_json(path.read_text(encoding="utf-8")) if path else Policy()


def run_discovery(args: argparse.Namespace) -> int:
    from .discovery import discover
    from .gemini import GeminiDecider
    from .provider import Budget, OpenAIDecider

    if not args.live:
        print(json.dumps({"status": "failure", "code": "live_opt_in_required"}))
        return 2
    if (
        args.output.exists()
        or args.events.exists()
        or args.output.resolve() == args.events.resolve()
        or (
            args.failure_screenshot is not None
            and (
                args.failure_screenshot.exists()
                or args.failure_screenshot.resolve()
                in {args.output.resolve(), args.events.resolve()}
            )
        )
    ):
        print(json.dumps({"status": "failure", "code": "choose_unused_output_paths"}))
        return 2
    try:
        inputs = Inputs(member_id=args.member_id)
        policy = load_policy(args.policy)
        # Budget path is fixed to this repository, not user-selectable per run.
        root = Path(__file__).resolve().parents[2]
        decider: OpenAIDecider | GeminiDecider
        factory = GeminiDecider if args.model.startswith("gemini-") else OpenAIDecider
        decider = factory(args.model, Budget(root / ".local" / "budget.json"))
    except (ValueError, OSError):
        print(json.dumps({"status": "failure", "code": "check_api_key_model_and_inputs"}))
        return 2
    events: list[dict[str, object]] = []
    with serve() as url:
        result, capability = discover(
            args.goal,
            inputs,
            url,
            decider,
            args.scenario,
            args.headed,
            events=events,
            failure_screenshot=args.failure_screenshot,
            policy=policy,
        )
    save_events(args.events, [*decider.events, *events], result)
    if capability:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(capability.model_dump_json(indent=2) + "\n")
    print(result.model_dump_json(indent=2))
    return 1 if result.status == "failure" else 0
