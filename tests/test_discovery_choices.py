import json

import pytest
from playwright.sync_api import sync_playwright
from test_discovery_handoff import FakeDecider

from interface_automation.cli import main
from interface_automation.demo import serve
from interface_automation.discovery import Decision, discover
from interface_automation.schema import Inputs
from interface_automation.surface import STEPS, Surface


def test_observation_preserves_alternatives_without_values() -> None:
    with serve() as url, sync_playwright() as driver:
        browser = driver.chromium.launch()
        surface = Surface(browser.new_page(), url, Inputs(member_id="12345"))
        try:
            surface.open("normal")
            initial = json.loads(surface.observe())
            assert set(initial["available_actions"]) == {"fill_member", "search"}
            assert not initial["member_input_matches_parameter"]
            surface.act(STEPS["fill_member"])
            filled = json.loads(surface.observe())
            assert filled["member_input_matches_parameter"]
            assert set(filled["available_actions"]) == {"fill_member", "search"}
            surface.act(STEPS["search"])
            result = surface.observe()
            assert set(json.loads(result)["available_actions"]) == {
                "fill_member",
                "search",
                "open_accounts",
            }
            assert "12345" not in result
        finally:
            browser.close()


def test_repetitive_model_still_stops_at_step_limit() -> None:
    class Repetitive(FakeDecider):
        def decide(self, goal: str, observation: str) -> Decision:
            assert "fill_member" in json.loads(observation)["available_actions"]
            return Decision(action="fill_member")

    with serve() as url:
        result, artifact = discover(
            "Read savings balance", Inputs(member_id="12345"), url, Repetitive(), max_steps=3
        )
    assert result.code == "step_limit"
    assert result.step == 3
    assert artifact is None


def test_unknown_target_rejected_before_live_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "automation",
            "discover",
            "--goal",
            "balance",
            "--target",
            "external-bank",
            "--member-id",
            "12345",
            "--model",
            "gemini-2.5-flash",
            "--output",
            "unused.json",
            "--events",
            "unused.jsonl",
            "--live",
        ],
    )
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2


def test_no_progress_stops_before_another_model_request() -> None:
    class Repetitive(FakeDecider):
        def decide(self, goal: str, observation: str) -> Decision:
            state = json.loads(observation)
            assert state["recent_actions"] == ["fill_member"] * self.calls
            self.calls += 1
            return Decision(action="fill_member")

    decider = Repetitive()
    with serve() as url:
        result, artifact = discover("Read balance", Inputs(member_id="12345"), url, decider)
    assert result.code == "no_progress"
    assert decider.calls == 3
    assert artifact is None
    assert result.expected and result.observed
