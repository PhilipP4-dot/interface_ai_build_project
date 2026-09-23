import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from interface_automation.demo import serve
from interface_automation.discovery import Decision, discover
from interface_automation.policy import Policy
from interface_automation.replay import replay
from interface_automation.schema import Capability, Inputs
from interface_automation.surface import UPDATE_STEPS, Stopped, Surface


def artifact():
    return Capability.model_validate_json(Path("artifacts/update_savings_balance.json").read_text())


class UpdateDecider:
    provenance = "offline_test"

    def __init__(self):
        self.actions = iter(UPDATE_STEPS)

    def decide(self, goal, observation):
        action = next(self.actions)
        assert action in json.loads(observation)["available_actions"]
        return Decision(action=action)


def test_update_discovery_and_different_input_replay():
    events = []
    with serve() as url:
        result, saved = discover(
            "Set savings balance",
            Inputs(member_id="12345", new_balance="501.5"),
            url,
            UpdateDecider(),
            events=events,
        )
        assert result.outputs == {"balance": "501.50"}
        assert saved is not None and saved.name == "update_savings_balance"
        assert saved.schema_version == "1.2"
        assert "501.5" not in saved.model_dump_json() + json.dumps(events)
        assert replay(saved, Inputs(member_id="67890", new_balance="0"), url).outputs == {
            "balance": "0.00"
        }
        assert (
            replay(saved, Inputs(member_id="99999", new_balance="1"), url).code
            == "member_not_found"
        )
        assert (
            replay(saved, Inputs(member_id="12345", new_balance="1"), url, policy=Policy()).code
            == "action_blocked"
        )
        assert replay(saved, Inputs(member_id="12345"), url).code == "workflow_inputs_mismatch"


@pytest.mark.parametrize("amount", ["-1", "1.001", "1e3", "1000000000", "", "NaN"])
def test_invalid_amount(amount):
    with pytest.raises(ValueError):
        Inputs(member_id="12345", new_balance=amount)


def test_update_checks_identity_and_never_repeats_write():
    with serve() as url, sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page()
        surface = Surface(page, url, Inputs(member_id="12345", new_balance="50"))
        surface.open("normal")
        for key in ("fill_member", "search", "open_accounts", "fill_balance"):
            surface.act(UPDATE_STEPS[key])
        page.get_by_role("textbox", name="Member ID", exact=True).fill("67890")
        with pytest.raises(Stopped) as exc:
            surface.act(UPDATE_STEPS["update_balance"])
        assert exc.value.result.code == "update_precondition_failed"
        assert (
            page.get_by_role("status", name="Savings balance", exact=True).inner_text() == "1250.75"
        )
        page.get_by_role("textbox", name="Member ID", exact=True).fill("12345")
        surface.act(UPDATE_STEPS["update_balance"])
        with pytest.raises(Stopped) as exc:
            surface.act(UPDATE_STEPS["update_balance"])
        assert exc.value.result.code == "update_already_applied"
        surface.act(UPDATE_STEPS["read_balance"])
        assert surface.finish().outputs == {"balance": "50.00"}
        browser.close()


def test_schema_rejects_update_without_readback():
    data = artifact().model_dump()
    data["steps"] = data["steps"][:-1]
    with pytest.raises(ValueError):
        Capability.model_validate(data)
