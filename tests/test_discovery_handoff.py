import json
from pathlib import Path
from typing import Literal

import pytest
from playwright.sync_api import Page
from test_replay import capability

from interface_automation.demo import serve
from interface_automation.discovery import Decision, discover
from interface_automation.provider import Budget
from interface_automation.replay import replay
from interface_automation.schema import Inputs


class FakeDecider:
    provenance: Literal["llm_discovery", "offline_test"] = "offline_test"

    def __init__(self) -> None:
        self.calls = 0

    def decide(self, goal: str, observation: str) -> Decision:
        self.calls += 1
        if json.loads(observation)["balance_extracted"]:
            return Decision(action="finish")
        if "read_balance" in observation:
            return Decision(action="read_balance")
        if "open_accounts" in observation:
            return Decision(action="open_accounts")
        if json.loads(observation)["member_input_present"]:
            return Decision(action="search")
        return Decision(action="fill_member")


def test_discovery_artifact_replays_new_input() -> None:
    decider = FakeDecider()
    with serve() as url:
        result, artifact = discover("Read savings balance", Inputs(member_id="12345"), url, decider)
        assert result.status == "success"
        assert decider.calls == 4
        assert artifact is not None and artifact.provenance == "offline_test"
        assert "12345" not in artifact.model_dump_json()
        second = replay(artifact, Inputs(member_id="67890"), url)
        assert second.outputs == {"balance": "842.10"}


def test_no_artifact_on_premature_finish_or_step_limit() -> None:
    class Premature(FakeDecider):
        def decide(self, goal: str, observation: str) -> Decision:
            return Decision(action="finish")

    with serve() as url:
        result, artifact = discover(
            "Read savings balance", Inputs(member_id="12345"), url, Premature()
        )
        assert result.status == "failure" and artifact is None
        result, artifact = discover(
            "Read savings balance", Inputs(member_id="12345"), url, FakeDecider(), max_steps=1
        )
        assert result.code == "step_limit" and artifact is None


def test_live_session_handoff_and_sanitized_events() -> None:
    def operator(page: Page) -> None:
        assert page.get_by_role("textbox").input_value() == "12345"
        page.get_by_role("button", name="Continue review", exact=True).click()
        page.get_by_role("button", name="Resume automation", exact=True).click()

    events: list[dict[str, object]] = []
    with serve() as url:
        result = replay(
            capability(),
            Inputs(member_id="12345"),
            url,
            "manual_review",
            operator=operator,
            events=events,
        )
    assert result.status == "success"
    kinds = [event["event"] for event in events]
    assert kinds.index("intervention") < kinds.index("human_action") < kinds.index("resumed")
    assert "12345" not in json.dumps(events) and "1250.75" not in json.dumps(events)


def test_resume_without_review_fails_closed() -> None:
    def operator(page: Page) -> None:
        page.get_by_role("button", name="Resume automation", exact=True).click()

    with serve() as url:
        result = replay(
            capability(), Inputs(member_id="12345"), url, "manual_review", operator=operator
        )
    assert result.code == "resume_state_invalid"


def test_headless_requires_operator() -> None:
    with serve() as url:
        result = replay(capability(), Inputs(member_id="12345"), url, "manual_review")
    assert result.code == "operator_required"


def test_budget_persists_and_stops(tmp_path: Path) -> None:
    ledger = tmp_path / "budget.json"
    first = Budget(ledger)
    for _ in range(10):
        first.reserve()
    with pytest.raises(RuntimeError):
        first.reserve()
    assert json.loads(ledger.read_text())["reserved_cents"] == 100


def test_budget_rejects_concurrent_use(tmp_path: Path) -> None:
    ledger = tmp_path / "budget.json"
    ledger.with_suffix(".lock").touch()
    with pytest.raises(FileExistsError):
        Budget(ledger).reserve()
