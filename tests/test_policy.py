from pathlib import Path

from test_discovery_handoff import FakeDecider
from test_replay import capability

from interface_automation.demo import serve
from interface_automation.discovery import discover
from interface_automation.policy import Policy
from interface_automation.replay import replay
from interface_automation.schema import Inputs


def test_policy_blocks_replay_action() -> None:
    with serve() as url:
        result = replay(
            capability(),
            Inputs(member_id="12345"),
            url,
            policy=Policy(allowed_actions=["fill_member"]),
        )
    assert result.code == "action_blocked"
    assert result.outputs == {}


def test_policy_blocks_target() -> None:
    with serve() as url:
        result = replay(
            capability(), Inputs(member_id="12345"), url, policy=Policy(allowed_hosts=[])
        )
    assert result.code == "target_blocked"


def test_discovery_cannot_bypass_policy_and_captures_failure(tmp_path: Path) -> None:
    screenshot = tmp_path / "blocked.png"
    with serve() as url:
        result, artifact = discover(
            "Read balance",
            Inputs(member_id="12345"),
            url,
            FakeDecider(),
            policy=Policy(allowed_actions=[]),
            failure_screenshot=screenshot,
        )
    assert result.code == "action_blocked"
    assert result.step == 1
    assert artifact is None
    assert screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_configuration_cannot_expand_fixed_target_boundary() -> None:
    with serve():
        result = replay(
            capability(),
            Inputs(member_id="12345"),
            "https://example.com",
            policy=Policy(allowed_hosts=["example.com"]),
        )
    assert result.code == "target_blocked"
