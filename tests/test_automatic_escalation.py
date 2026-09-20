from playwright.sync_api import Page
from test_discovery_handoff import FakeDecider
from test_replay import capability

from interface_automation.demo import serve
from interface_automation.discovery import Decision, discover
from interface_automation.replay import replay
from interface_automation.schema import Inputs


def test_operator_can_advance_to_details() -> None:
    def operator(page: Page) -> None:
        page.get_by_role("button", name="Continue review").click()
        page.get_by_role("link", name="View accounts").click()
        page.get_by_role("button", name="Resume automation").click()

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
    assert result.outputs == {"balance": "1250.75"}
    assert any(e["event"] == "step_verified" for e in events)


def test_expired_session_escalates_automatically() -> None:
    def operator(page: Page) -> None:
        assert "session expired" in page.locator("#operator-handoff").inner_text()
        page.get_by_role("button", name="Restore session").click()
        page.get_by_role("link", name="View accounts").wait_for()
        page.get_by_role("button", name="Resume automation").click()

    with serve() as url:
        result = replay(
            capability(), Inputs(member_id="67890"), url, "session_expired", operator=operator
        )
    assert result.outputs == {"balance": "842.10"}


def test_changed_member_cannot_resume() -> None:
    def operator(page: Page) -> None:
        page.get_by_role("button", name="Continue review").click()
        page.get_by_role("textbox").fill("67890")
        page.get_by_role("button", name="Resume automation").click()

    with serve() as url:
        result = replay(
            capability(), Inputs(member_id="12345"), url, "manual_review", operator=operator
        )
    assert result.code == "resume_state_invalid"


def test_no_progress_records_verified_navigation() -> None:
    class Stuck(FakeDecider):
        def decide(self, goal: str, observation: str) -> Decision:
            if "read_balance" in observation:
                return Decision(action="read_balance")
            return Decision(action="fill_member")

    def operator(page: Page) -> None:
        page.get_by_role("button", name="Search", exact=True).click()
        page.get_by_role("link", name="View accounts").click()
        page.get_by_role("button", name="Resume automation").click()

    events: list[dict[str, object]] = []
    with serve() as url:
        result, artifact = discover(
            "Read balance",
            Inputs(member_id="12345"),
            url,
            Stuck(),
            operator=operator,
            events=events,
        )
    assert result.status == "success"
    assert artifact is not None
    with serve() as url:
        assert replay(artifact, Inputs(member_id="67890"), url).outputs == {"balance": "842.10"}
    assert any(e.get("reason") == "no_progress" for e in events)
    assert artifact.schema_version == "1.1"


def test_missing_control_automatically_requests_operator(monkeypatch) -> None:
    from playwright.sync_api import TimeoutError

    from interface_automation.surface import Surface

    original = Surface.act
    failed = False

    def action(self, step):
        nonlocal failed
        if step.name == "Search" and not failed:
            failed = True
            raise TimeoutError("synthetic unavailable control")
        original(self, step)

    monkeypatch.setattr(Surface, "act", action)

    def operator(page: Page) -> None:
        assert "ui unavailable" in page.locator("#operator-handoff").inner_text()
        page.get_by_role("button", name="Search", exact=True).click()
        page.get_by_role("link", name="View accounts").wait_for()
        page.get_by_role("button", name="Resume automation").click()

    with serve() as url:
        result = replay(capability(), Inputs(member_id="12345"), url, operator=operator)
    assert result.status == "success"


def test_manual_takeover_during_normal_replay() -> None:
    from threading import Event

    pause = Event()
    pause.set()
    events: list[dict[str, object]] = []

    def operator(page: Page) -> None:
        assert "manual takeover" in page.locator("#operator-handoff").inner_text()
        page.get_by_role("textbox").fill("12345")
        page.get_by_role("button", name="Search", exact=True).click()
        page.get_by_role("link", name="View accounts").click()
        page.get_by_role("button", name="Resume automation").click()

    with serve() as url:
        result = replay(
            capability(),
            Inputs(member_id="12345"),
            url,
            operator=operator,
            pause_request=pause,
            events=events,
        )
    assert result.status == "success"
    assert any(e.get("reason") == "manual_takeover" for e in events)
    assert not pause.is_set()


def test_learned_review_replays_conditionally() -> None:
    def operator(page: Page) -> None:
        page.get_by_role("button", name="Continue review").click()
        page.get_by_role("link", name="View accounts").click()
        page.get_by_role("button", name="Resume automation").click()

    artifact = capability()
    with serve() as url:
        assert (
            replay(
                artifact, Inputs(member_id="12345"), url, "manual_review", operator=operator
            ).status
            == "success"
        )
        assert artifact.schema_version == "1.1"
        assert len(artifact.recoveries) == 1
        events: list[dict[str, object]] = []
        assert replay(
            artifact, Inputs(member_id="67890"), url, "manual_review", events=events
        ).outputs == {"balance": "842.10"}
        assert any(e["event"] == "recovery_replayed" for e in events)
        assert not any(e["event"] == "intervention" for e in events)
        assert replay(artifact, Inputs(member_id="67890"), url).status == "success"
    assert "12345" not in artifact.model_dump_json()


def test_learned_session_restore_replays_without_operator() -> None:
    def operator(page: Page) -> None:
        page.get_by_role("button", name="Restore session").click()
        page.get_by_role("link", name="View accounts").wait_for()
        page.get_by_role("button", name="Resume automation").click()

    artifact = capability()
    with serve() as url:
        assert (
            replay(
                artifact, Inputs(member_id="12345"), url, "session_expired", operator=operator
            ).status
            == "success"
        )
        assert replay(artifact, Inputs(member_id="67890"), url, "session_expired").outputs == {
            "balance": "842.10"
        }


def test_unknown_human_action_is_not_saved_as_repair() -> None:
    def operator(page: Page) -> None:
        page.evaluate(
            "const b=document.createElement('button');b.textContent='Unknown operation';document.body.append(b)"
        )
        page.get_by_role("button", name="Unknown operation").click()
        page.get_by_role("button", name="Continue review").click()
        page.get_by_role("button", name="Resume automation").click()

    artifact = capability()
    with serve() as url:
        result = replay(
            artifact, Inputs(member_id="12345"), url, "manual_review", operator=operator
        )
    assert result.status == "success"
    assert artifact.recoveries == []
    assert artifact.schema_version == "1.0"


def test_assisted_discovery_emits_replayable_conditional_fix() -> None:
    def operator(page: Page) -> None:
        page.get_by_role("button", name="Continue review").click()
        page.get_by_role("link", name="View accounts").click()
        page.get_by_role("button", name="Resume automation").click()

    with serve() as url:
        result, artifact = discover(
            "Read savings balance",
            Inputs(member_id="12345"),
            url,
            FakeDecider(),
            scenario="manual_review",
            operator=operator,
        )
        assert result.status == "success" and artifact is not None
        assert artifact.schema_version == "1.1"
        assert len(artifact.steps) == 4 and len(artifact.recoveries) == 1
        assert replay(artifact, Inputs(member_id="67890"), url, "manual_review").outputs == {
            "balance": "842.10"
        }


def test_balance_field_is_not_recorded_as_member_input():
    def operator(page: Page) -> None:
        page.get_by_role("button", name="Continue review").click()
        page.get_by_role("link", name="View accounts").click()
        page.get_by_role("textbox", name="New savings balance (USD)").fill("50")
        page.get_by_role("button", name="Resume automation").click()

    artifact = capability()
    events = []
    with serve() as url:
        result = replay(
            artifact,
            Inputs(member_id="12345"),
            url,
            "manual_review",
            operator=operator,
            events=events,
        )
    assert result.status == "success"
    assert artifact.recoveries == []
    assert any(e.get("control") == "other" and e.get("kind") == "input" for e in events)
