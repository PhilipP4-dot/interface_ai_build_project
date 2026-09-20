import json
from pathlib import Path

from playwright.sync_api import Page
from test_replay import capability

from interface_automation.cli import save_events
from interface_automation.demo import serve
from interface_automation.replay import replay
from interface_automation.schema import Inputs, Result


def test_result_log_excludes_outputs(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    save_events(
        path,
        [],
        Result(
            status="failure", code="output_missing", step=4, outputs={"balance": "sensitive-value"}
        ),
    )
    value = json.loads(path.read_text())
    assert value["step"] == 4
    assert value["expected"] and value["observed"]
    assert "sensitive-value" not in path.read_text()
    assert "outputs" not in value


def test_missing_output_captures_failure(tmp_path: Path) -> None:
    artifact = capability()
    artifact.steps = artifact.steps[:-1]
    with serve() as url:
        result = replay(
            artifact, Inputs(member_id="12345"), url, failure_screenshot=tmp_path / "missing.png"
        )
    assert result.code == "output_missing"
    assert result.step == 3
    assert result.expected and result.observed
    assert (tmp_path / "missing.png").read_bytes().startswith(b"\x89PNG")


def test_handoff_context_in_panel_and_events() -> None:
    def operator(page: Page) -> None:
        panel = page.locator("#operator-handoff").inner_text()
        assert "Savings balance lookup (replay), step 2" in panel
        assert "12345" not in panel
        page.get_by_role("button", name="Continue review", exact=True).click()
        page.get_by_role("button", name="Resume automation", exact=True).click()

    events: list[dict[str, object]] = []
    with serve() as url:
        result = replay(
            capability(),
            Inputs(member_id="12345"),
            url,
            scenario="manual_review",
            operator=operator,
            events=events,
        )
    assert result.status == "success"
    intervention = next(event for event in events if event["event"] == "intervention")
    assert intervention["step"] == 2
    assert intervention["capability"] == "savings_balance"
    assert intervention["state"]
    assert "12345" not in json.dumps(events)
