from pathlib import Path

import pytest
from pydantic import ValidationError

from interface_automation.demo import serve
from interface_automation.replay import permitted, replay
from interface_automation.schema import Capability, Inputs


def capability() -> Capability:
    return Capability.model_validate_json(Path("artifacts/savings_balance.json").read_text())


@pytest.mark.parametrize("member,balance", [("12345", "1250.75"), ("67890", "842.10")])
def test_parameterized_replay(member: str, balance: str) -> None:
    with serve() as url:
        result = replay(capability(), Inputs(member_id=member), url)
    assert result.status == "success"
    assert result.outputs == {"balance": balance}


@pytest.mark.parametrize(
    "member,scenario,status,code",
    [
        ("99999", "normal", "business_outcome", "member_not_found"),
        ("12345", "permission_denied", "failure", "permission_denied"),
        ("12345", "session_expired", "failure", "operator_required"),
        ("12345", "slow", "success", "completed"),
    ],
)
def test_runtime_conditions(member: str, scenario: str, status: str, code: str) -> None:
    with serve() as url:
        result = replay(capability(), Inputs(member_id=member), url, scenario)
    assert (result.status, result.code) == (status, code)


def test_checkpoint_failure() -> None:
    flow = capability()
    flow.checkpoint = "Wrong checkpoint"
    with serve() as url:
        result = replay(flow, Inputs(member_id="12345"), url)
    assert result.code == "ui_failure"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://127.0.0.1:8765/private",
        "http://127.0.0.1:9999",
        "http://user@127.0.0.1:8765",
    ],
)
def test_allowlist(url: str) -> None:
    assert not permitted(url, "http://127.0.0.1:8765")


def test_invalid_input_and_schema() -> None:
    with pytest.raises(ValidationError):
        Inputs(member_id="<script>")
    data = capability().model_dump()
    data["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        Capability.model_validate(data)
