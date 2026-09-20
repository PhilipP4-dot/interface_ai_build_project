import json
import re
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from playwright.sync_api import sync_playwright
from test_replay import capability

from interface_automation.dashboard import Dashboard, RunRequest, make_server


def fixture_root(tmp_path: Path) -> Path:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "sample.json").write_text(capability().model_dump_json())
    return tmp_path


def test_dashboard_rejects_untrusted_requests(tmp_path: Path) -> None:
    server = make_server(fixture_root(tmp_path), 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(url) as response:
            html = response.read().decode()
        token = re.search("const token='([^']+)'", html).group(1)
        for headers in [
            {},
            {"X-Dashboard-Token": token, "Origin": "https://untrusted.test"},
            {"X-Dashboard-Token": token, "Host": "untrusted.test"},
        ]:
            with pytest.raises(HTTPError) as error:
                urlopen(Request(url + "/api/state", headers=headers))
            assert error.value.code == 403
        with urlopen(Request(url + "/api/state", headers={"X-Dashboard-Token": token})) as response:
            assert len(json.load(response)["workflows"]) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_dashboard_validates_consent_paths_and_active_run(tmp_path: Path) -> None:
    manager = Dashboard(fixture_root(tmp_path))
    for request in [
        RunRequest(mode="discover", member_id="12345"),
        RunRequest(mode="replay", member_id="12345", workflow="../../.env"),
    ]:
        with pytest.raises(ValueError):
            manager.start(request)
    manager.active = "existing"
    with pytest.raises(ValueError):
        manager.start(
            RunRequest(mode="replay", member_id="12345", workflow="artifacts/sample.json")
        )


def test_dashboard_browser_replay_and_history(tmp_path: Path) -> None:
    root = fixture_root(tmp_path)
    server = make_server(root, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1000})
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.wait_for_function("Boolean(state.demo_url)")
            assert page.locator("#workflow").input_value() == ""
            assert page.locator("#replayInputs input").count() == 0
            assert page.locator("#targetSettings").is_hidden()
            assert page.locator("#start").is_disabled()
            page.locator("#workflow").select_option("artifacts/sample.json")
            page.get_by_role("button", name="Use demo site", exact=True).click()
            assert page.locator("#targetUrl").input_value().startswith("http://127.0.0.1:")
            page.locator("#member").fill("67890")
            page.get_by_role("button", name="Run saved workflow", exact=True).click()
            page.get_by_text("$842.10", exact=True).wait_for(timeout=30000)
            assert page.locator("#status").inner_text() == "Completed"
            folder = Path("runs/dashboard-preview")
            folder.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(folder / "dashboard.png"), full_page=True)
            page.locator("#member").fill("99999")
            page.get_by_role("button", name="Run saved workflow", exact=True).click()
            page.get_by_text(
                "The lookup worked; no matching customer was found.", exact=True
            ).wait_for(timeout=30000)
            page.get_by_role("button", name="Create a workflow", exact=True).click()
            assert page.locator("#replayInputs").is_hidden()
            page.locator("#live").check()
            page.get_by_role("button", name="Discover and save workflow", exact=True).click()
            page.locator("#inputQuestion").wait_for(state="visible")
            page.get_by_role("button", name="Cancel", exact=True).click()
            page.get_by_text("Cancelled", exact=True).wait_for()

            # Exercise the renderer contract with a different workflow's input metadata.
            def alternative_fields(route):
                response = route.fetch()
                data = response.json()
                other = dict(data["workflows"][0])
                other.update(
                    id="other",
                    name="Other workflow",
                    inputs=[
                        {
                            "key": "reference",
                            "label": "Reference",
                            "type": "text",
                            "required": True,
                        },
                        {
                            "key": "amount",
                            "label": "Amount",
                            "type": "number",
                            "min": "0",
                            "step": "0.01",
                            "required": True,
                        },
                    ],
                )
                data["workflows"].append(other)
                route.fulfill(response=response, json=data)

            page.route("**/api/state", alternative_fields)
            page.reload()
            page.locator("#workflow option[value='other']").wait_for(state="attached")
            page.locator("#workflow").select_option("other")
            assert page.get_by_label("Reference", exact=True).get_attribute("maxlength") is None
            assert page.get_by_label("Amount", exact=True).get_attribute("step") == "0.01"
            assert page.locator("#replayInputs input").count() == 2
            page.locator("#workflow").select_option("artifacts/sample.json")
            assert page.locator("#replayInputs input").count() == 1
            page.locator("#workflow").select_option("")
            assert page.locator("#replayInputs input").count() == 0
            browser.close()
        summaries = list((root / "runs/dashboard").glob("*/summary.json"))
        assert len(summaries) == 2
        for summary in summaries:
            text = summary.read_text()
            assert "842.10" not in text and "67890" not in text and "99999" not in text
        restored = Dashboard(root).snapshot()
        assert len(restored["runs"]) == 2
        assert all(not run["outputs_available"] for run in restored["runs"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_dashboard_discovery_saves_reusable_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_discovery_handoff import FakeDecider

    class OfflineDecider(FakeDecider):
        def __init__(self, *args: object):
            super().__init__()
            self.events: list[dict[str, object]] = []

    monkeypatch.setattr("interface_automation.dashboard.GeminiDecider", OfflineDecider)
    manager = Dashboard(fixture_root(tmp_path))
    request = RunRequest(mode="discover", member_id="12345", live=True)
    run = {"id": "test", "mode": "discover", "status": "running", "events": [], "created": "test"}
    folder = manager.directory / "test"
    folder.mkdir()
    manager.runs["test"] = run
    manager.active = "test"
    manager.execute(request, None, run, folder)
    assert run["status"] == "success"
    assert manager.active is None
    assert manager.workflows()["runs/dashboard/test/capability.json"].provenance == "offline_test"
    assert len([e for e in run["events"] if e["event"] == "action"]) == 4
    assert "12345" not in (folder / "events.jsonl").read_text()


def test_pause_rejects_stale_or_inactive_runs(tmp_path: Path) -> None:
    manager = Dashboard(fixture_root(tmp_path))
    with pytest.raises(ValueError):
        manager.request_pause("missing")
    manager.active = "current"
    manager.runs["current"] = {"status": "running"}
    with pytest.raises(ValueError):
        manager.request_pause("old")
    manager.request_pause("current")
    assert manager.pause_request.is_set()
    assert manager.runs["current"]["pause_pending"]
    manager.runs["current"]["status"] = "needs_review"
    with pytest.raises(ValueError):
        manager.request_pause("current")


def test_dashboard_saves_repaired_version_without_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from playwright.sync_api import Page

    from interface_automation.replay import replay

    manager = Dashboard(fixture_root(tmp_path))
    source = tmp_path / "artifacts/sample.json"
    original = source.read_bytes()

    def operator(page: Page) -> None:
        page.get_by_role("button", name="Continue review").click()
        page.get_by_role("button", name="Resume automation").click()

    def execute(*args, **kwargs):
        return replay(*args, **kwargs, operator=operator)

    monkeypatch.setattr("interface_automation.dashboard.replay", execute)
    run = {"id": "repair", "mode": "replay", "status": "running", "events": [], "created": "test"}
    folder = manager.directory / "repair"
    folder.mkdir()
    manager.runs["repair"] = run
    manager.active = "repair"
    manager.execute(
        RunRequest(
            mode="replay",
            member_id="12345",
            workflow="artifacts/sample.json",
            scenario="manual_review",
        ),
        capability(),
        run,
        folder,
    )
    updated = manager.workflows()["runs/dashboard/repair/capability.json"]
    assert len(updated.recoveries) == 1 and updated.schema_version == "1.1"
    assert source.read_bytes() == original


@pytest.mark.parametrize("supplied", [False, True])
def test_goal_only_discovery_review_and_generated_inputs(tmp_path, monkeypatch, supplied):
    from interface_automation.schema import Result

    manager = Dashboard(fixture_root(tmp_path))

    def fake_discover(*args, **kwargs):
        assert args[1].member_id == "12345"
        return Result(status="success", code="completed"), capability()

    monkeypatch.setattr("interface_automation.dashboard.discover", fake_discover)

    class FakeModel:
        def __init__(self, *args):
            pass

    monkeypatch.setattr("interface_automation.dashboard.GeminiDecider", FakeModel)
    goal = (
        "Read the member 12345's savings balance" if supplied else "Read the member savings balance"
    )
    run_id = manager.start(RunRequest(mode="discover", live=True, goal=goal))
    if supplied:
        assert run_id not in manager.pending
    else:
        assert manager.runs[run_id]["status"] == "needs_input"
        with pytest.raises(ValueError):
            manager.answer(run_id, "invalid")
        assert run_id in manager.pending
        manager.answer(run_id, "12345")
    import time

    deadline = time.monotonic() + 10
    while manager.active and time.monotonic() < deadline:
        time.sleep(0.05)
    assert manager.active is None
    assert manager.runs[run_id]["draft"]["inputs"][0]["key"] == "member_id"
    path = manager.directory / run_id / "capability.json"
    assert not path.exists()
    manager.review(run_id, True)
    assert path.exists()
    assert "12345" not in path.read_text()
    assert manager.snapshot()["workflows"][0]["inputs"][0]["key"] == "member_id"
    with pytest.raises(ValueError):
        manager.review(run_id, True)
    second = manager.start(RunRequest(mode="discover", live=True))
    manager.cancel_input(second)
    assert manager.active is None
    assert second not in manager.pending


@pytest.mark.parametrize(
    "goal, expected",
    [
        ("Read the member 12345's savings balance", "12345"),
        ("Read 12345's savings balance", "12345"),
        ("Read 12345’s savings balance", "12345"),
        ("Read customer ID: 01234 savings", "01234"),
        ("Read member #67890 balance", "67890"),
        ("Read the member savings balance", None),
        ("Read member 123456 balance", None),
        ("Read member 12345 or member 67890 balance", None),
        ("Find balance above 12345", None),
        ("Read member 12345.67 balance", None),
    ],
)
def test_member_from_goal(goal, expected):
    from interface_automation.dashboard import member_from_goal

    assert member_from_goal(goal) == expected
