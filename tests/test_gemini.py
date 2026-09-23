import io
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from interface_automation.gemini import GeminiDecider
from interface_automation.provider import Budget
from interface_automation.surface import Stopped


@pytest.mark.parametrize("model_name", ["gemini-3.5-flash", "gemini-2.5-flash"])
def test_page_decision_uses_shared_transport_without_bank_action_catalog(
    tmp_path, monkeypatch, model_name
):
    from interface_automation.page_workflow import PageDecision

    monkeypatch.setenv("AI_API_KEY", "test-key")
    payloads = []

    def transport(request, timeout):
        payloads.append(json.loads(request.data))
        return io.BytesIO(
            json.dumps(
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [
                                    {"text": '{"action":"fill","target":"c0","value":"PK-123"}'}
                                ]
                            },
                        }
                    ]
                }
            ).encode()
        )

    monkeypatch.setattr("interface_automation.gemini.urlopen", transport)
    model = GeminiDecider(model_name, Budget(tmp_path / "budget.json"), tmp_path / ".env")
    result = model.structured("Choose an observed control", '{"goal":"Find PK-123"}', PageDecision)
    assert result.target == "c0" and result.value == "PK-123"
    schema = payloads[0]["generationConfig"]["responseJsonSchema"]
    assert schema["properties"]["action"]["enum"] == ["fill", "click", "read", "ask"]
    assert "member" not in json.dumps(payloads)
    assert "PK-123" not in json.dumps(model.events)


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    now = [0.0]
    monkeypatch.setattr("interface_automation.gemini.monotonic", lambda: now[0])
    monkeypatch.setattr(
        "interface_automation.gemini.sleep", lambda seconds: now.__setitem__(0, now[0] + seconds)
    )
    return now


def test_requests_are_spaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_clock: list[float]
) -> None:
    from interface_automation.discovery import Decision

    monkeypatch.setenv("AI_API_KEY", "test-key")
    starts: list[float] = []

    def decision(self: GeminiDecider, goal: str, observation: str) -> Decision:
        starts.append(fake_clock[0])
        return Decision(action="search")

    monkeypatch.setattr(GeminiDecider, "_decide_once", decision)
    decider = GeminiDecider("gemini-2.5-flash", Budget(tmp_path / "budget.json"), tmp_path / ".env")
    for _ in range(5):
        decider.decide("goal", "controls")
    assert starts == [0, 15, 30, 45, 60]


def test_retry_respects_delay_and_counts_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_clock: list[float]
) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")
    calls = [0]

    def transport(request: Request, timeout: int) -> io.BytesIO:
        calls[0] += 1
        if calls[0] == 1:
            body = {"error": {"details": [{"retryDelay": "25s"}]}}
            raise HTTPError(
                request.full_url, 429, "blocked", {}, io.BytesIO(json.dumps(body).encode())
            )  # type: ignore[arg-type]
        return io.BytesIO(
            b'{"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":"{\\"action\\":\\"search\\"}"}]}}]}'
        )

    monkeypatch.setattr("interface_automation.gemini.urlopen", transport)
    budget = Budget(tmp_path / "budget.json")
    decider = GeminiDecider("gemini-2.5-flash", budget, tmp_path / ".env")
    assert decider.decide("goal", "controls").action == "search"
    assert fake_clock[0] == 25 and budget.run_cents == 20


def test_quota_failure_is_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")

    def transport(request: Request, timeout: int) -> io.BytesIO:
        body = {
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "message": "private-provider-text",
                "details": [{"violations": [{"quotaValue": "5"}], "retryDelay": "3s"}],
            }
        }
        raise HTTPError(request.full_url, 429, "blocked", {}, io.BytesIO(json.dumps(body).encode()))  # type: ignore[arg-type]

    monkeypatch.setattr("interface_automation.gemini.urlopen", transport)
    decider = GeminiDecider("gemini-2.5-flash", Budget(tmp_path / "budget.json"), tmp_path / ".env")
    with pytest.raises(Stopped) as caught:
        decider.decide("goal", "controls")
    assert caught.value.result.code == "gemini_http_429"
    assert decider.events[0]["quota_limit"] == 5
    assert "private-provider-text" not in json.dumps(decider.events)
    assert "test-key" not in json.dumps(decider.events)


@pytest.mark.parametrize("model", ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash"])
def test_gemini_uses_named_key_and_validates_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    env = tmp_path / ".env"
    env.write_text("AI_API_KEY=synthetic-gemini-key\nOPENAI_API_KEY=wrong-provider-key")
    ledger = tmp_path / "budget.json"

    def transport(request: Request, timeout: int) -> io.BytesIO:
        assert (
            request.full_url
            == f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )
        assert request.get_header("X-goog-api-key") == "synthetic-gemini-key"
        assert "key=" not in request.full_url
        assert request.data is not None and timeout == 45
        payload = json.loads(request.data)
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        if model == "gemini-3.5-flash":
            assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "LOW"}
            assert "responseJsonSchema" in payload["generationConfig"]
        elif model == "gemini-2.5-flash":
            assert payload["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0
        else:
            assert "thinkingConfig" not in payload["generationConfig"]
            assert "responseJsonSchema" not in payload["generationConfig"]
            assert payload["generationConfig"]["responseSchema"]["propertyOrdering"] == ["action"]
        assert json.loads(ledger.read_text())["reserved_cents"] == 10
        return io.BytesIO(
            json.dumps(
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": '{"action":"search"}'}]},
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 100,
                        "candidatesTokenCount": 8,
                        "promptTokensDetails": [],
                    },
                }
            ).encode()
        )

    monkeypatch.setattr("interface_automation.gemini.urlopen", transport)
    decider = GeminiDecider(model, Budget(ledger), env)
    assert decider.decide("Synthetic goal", "controls").action == "search"
    assert "synthetic-gemini-key" not in json.dumps(decider.events)


@pytest.mark.parametrize(
    "response",
    [
        {"candidates": []},
        {
            "candidates": [
                {
                    "finishReason": "MAX_TOKENS",
                    "content": {"parts": [{"text": '{"action":"search"}'}]},
                }
            ]
        },
        {
            "candidates": [
                {"finishReason": "STOP", "content": {"parts": [{"text": '{"action":"delete"}'}]}}
            ]
        },
    ],
)
def test_gemini_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, response: dict[str, object]
) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-key")

    def transport(request: Request, timeout: int) -> io.BytesIO:
        return io.BytesIO(json.dumps(response).encode())

    monkeypatch.setattr("interface_automation.gemini.urlopen", transport)
    with pytest.raises(Stopped):
        GeminiDecider(
            "gemini-2.5-flash", Budget(tmp_path / "budget.json"), tmp_path / ".env"
        ).decide("goal", "controls")


@pytest.mark.parametrize("repair", [True, False])
def test_invalid_decision_retry_is_bounded(tmp_path, monkeypatch, fake_clock, repair):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    calls = []

    def transport(request, timeout):
        calls.append(request)
        decision = {"action": "fill_member"}
        if len(calls) == 1 or not repair:
            decision["value"] = "12345"
        return io.BytesIO(
            json.dumps(
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": json.dumps(decision)}]},
                        }
                    ]
                }
            ).encode()
        )

    monkeypatch.setattr("interface_automation.gemini.urlopen", transport)
    decider = GeminiDecider("gemini-2.5-flash", Budget(tmp_path / "budget.json"), tmp_path / ".env")
    if repair:
        assert (
            decider.decide("goal", '{"available_actions":["fill_member"]}').action == "fill_member"
        )
    else:
        with pytest.raises(Stopped) as exc:
            decider.decide("goal", '{"available_actions":["fill_member"]}')
        assert exc.value.result.code == "model_invalid_response"
    assert len(calls) == 2 and fake_clock[0] == 15
    assert decider.budget.run_cents == 20
    assert "12345" not in json.dumps(decider.events)
