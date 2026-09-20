import io
import json
from pathlib import Path
from urllib.request import Request

import pytest

from interface_automation.provider import Budget, OpenAIDecider


def test_transport_contract_and_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    ledger = tmp_path / "budget.json"

    def fake_request(request: Request, timeout: int) -> io.BytesIO:
        assert request.full_url == "https://api.openai.com/v1/responses"
        assert timeout == 45 and request.data is not None
        payload = json.loads(request.data)
        assert payload["store"] is False
        assert payload["max_output_tokens"] == 2048
        assert payload["text"]["format"]["strict"] is True
        assert payload["text"]["format"]["schema"]["required"] == ["action"]
        assert json.loads(ledger.read_text())["reserved_cents"] == 10
        return io.BytesIO(
            json.dumps(
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": '{"action":"search"}'}],
                        }
                    ],
                }
            ).encode()
        )

    monkeypatch.setattr("interface_automation.provider.urlopen", fake_request)
    assert (
        OpenAIDecider("gpt-5.4", Budget(ledger), tmp_path / ".env")
        .decide("Synthetic goal", "controls")
        .action
        == "search"
    )


def test_refusal_does_not_become_action(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")

    def refusal(request: Request, timeout: int) -> io.BytesIO:
        return io.BytesIO(
            b'{"status":"completed","output":[{"type":"message","content":[{"type":"refusal"}]}]}'
        )

    monkeypatch.setattr("interface_automation.provider.urlopen", refusal)
    with pytest.raises(ValueError):
        OpenAIDecider("gpt-5.4", Budget(tmp_path / "budget.json"), tmp_path / ".env").decide(
            "goal", "controls"
        )


def test_total_cap_survives_new_run(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text('{"reserved_cents":1990}')
    Budget(path).reserve()
    with pytest.raises(RuntimeError):
        Budget(path).reserve()
    assert json.loads(path.read_text())["reserved_cents"] == 2000
    assert not path.with_suffix(".lock").exists()


def test_unknown_model_fails_before_spending(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    with pytest.raises(ValueError):
        OpenAIDecider("unreviewed-model", Budget(path))
    assert not path.exists()
