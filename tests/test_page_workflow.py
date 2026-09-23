import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import TypeVar

import pytest
from pydantic import BaseModel

from interface_automation.page_workflow import FieldSpec, PageCapability, run_page, simulator_url
from interface_automation.schema import Result
from interface_automation.surface import Stopped

T = TypeVar("T", bound=BaseModel)


def test_dependent_select_options_refresh_without_another_model_call():
    html = """<label for="region">Region</label><select id="region" onchange="city.options[0].remove()"><option>North</option><option>South</option></select>
    <label for="city">City</label><select id="city"><option>Old city</option><option>Harbor</option></select>
    <output aria-label="Result">Harbor</output>"""

    class BatchModel(ScriptedDecider):
        def structured(self, instructions, observation, contract):
            result = super().structured(instructions, observation, contract)
            if contract.__name__ == "PageDecision" and result.action == "fill":
                city = next(c for c in json.loads(observation)["controls"] if c["name"] == "City")
                return contract.model_validate(
                    {
                        **result.model_dump(),
                        "additional_fills": [{"target": city["id"], "value": "Harbor"}],
                    }
                )
            return result

    model = BatchModel([("fill", "Region", "South"), ("read", "Result", None)])
    with fixture_site(html) as url:
        result, cap = run_page(url, goal="Read Harbor in South", decider=model)
    assert result.status == "success" and cap is not None
    assert len(model.observations) == 2
    assert cap.inputs[1].options == [{"value": "Harbor", "label": "Harbor"}]


@pytest.mark.parametrize("navigate", [False, True])
def test_discovery_handoff_preserves_session_and_never_saves_unrecorded_repair(navigate):
    html = '<input aria-label="Marker" value="session-value"><output aria-label="Status">Ready</output>'

    class StuckModel(ScriptedDecider):
        stuck = True

        def structured(self, instructions, observation, contract):
            if self.stuck:
                self.stuck = False
                raise Stopped(Result(status="failure", code="no_progress"))
            return super().structured(instructions, observation, contract)

    def operator(page):
        assert page.get_by_label("Marker").input_value() == "session-value"
        page.get_by_label("Marker").fill("PRIVATE-REPAIR")
        if navigate:
            page.goto(page.url + "/next")
        page.get_by_role("button", name="Resume automation", exact=True).click()

    events = []
    with fixture_site(html) as url:
        result, cap = run_page(
            url,
            goal="Read status",
            decider=StuckModel([("read", "Status", None)]),
            operator=operator,
            events=events,
        )
    assert result.status == "success" and cap is None, result
    assert any(e["event"] == "intervention" for e in events)
    assert any(e["event"] == "resumed" for e in events)
    assert any(e["event"] == "human_action" for e in events)
    assert any(e["event"] == "capability_not_saved" for e in events)
    assert "PRIVATE-REPAIR" not in json.dumps(events)


@pytest.mark.parametrize("cancel", [False, True])
def test_discovery_handoff_deadline_and_cancel(monkeypatch, cancel):
    monkeypatch.setattr("interface_automation.page_workflow.CONTROL_WAIT_SECONDS", 0.1)
    monkeypatch.setattr("interface_automation.page_workflow.HUMAN_WAIT_SECONDS", 0.2)

    def operator(page):
        if cancel:
            page.get_by_role("button", name="Stop discovery", exact=True).click()

    with fixture_site("<p>Loading</p>") as url:
        result, cap = run_page(url, decider=ScriptedDecider([]), operator=operator)
    assert result.code == ("operator_cancelled" if cancel else "intervention_timeout")
    assert cap is None


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://www.ngpf.org/bank-sim/transfer", True),
        ("https://www.ngpf.org/bank-sim/", True),
        ("https://www.ngpf.org/account", False),
        ("https://www.ngpf.org/bank-simulator/", False),
        ("https://www.ngpf.org/bank-sim/%2e%2e/account", False),
        ("https://www.ngpf.org.evil.test/bank-sim/", False),
        ("http://www.ngpf.org/bank-sim/", False),
    ],
)
def test_simulator_permission_scope(url, allowed):
    assert simulator_url(url) is allowed


def test_unseen_simulator_form_batches_fields_and_verifies_replay(monkeypatch):
    html = """<a onclick="stockPanel.hidden=false;this.hidden=true">Allocate stock</a>
    <div id="stockPanel" hidden>
    <div role="combobox" aria-label="Warehouse" tabindex="0" id="warehouse" style="padding:10px"
      onclick="choices.hidden=false" onkeydown="if(event.key==='Escape')setTimeout(()=>choices.hidden=true,150)"></div>
    <div id="choices" role="listbox" hidden>
    <div role="option" onclick="warehouse.textContent='North';choices.hidden=true">North</div>
    <div role="option" onclick="warehouse.textContent='South';choices.hidden=true">South</div></div>
    <label>Quantity<input id="quantity" type="number"></label>
    <button onclick="stockPanel.hidden=true;receipt.hidden=false;receipt.textContent='Allocated '+quantity.value+' units to '+warehouse.textContent">Allocate</button>
    </div><output id="receipt" aria-label="Receipt" hidden></output>"""

    class AllocationModel(ScriptedDecider):
        def structured(self, instructions, observation, contract):
            observed = json.loads(observation)
            if contract.__name__ == "GoalAssessment":
                assert observed["simulator_commit_executed"]
                return contract.model_validate({"outcome": "achieved", "requires_change": True})
            result = super().structured(instructions, observation, contract)
            if result.action == "fill":
                quantity = next(c for c in observed["controls"] if c["name"] == "Quantity")
                return contract.model_validate(
                    {
                        **result.model_dump(),
                        "additional_fills": [{"target": quantity["id"], "value": "20"}],
                    }
                )
            if result.action == "click" and len(self.observations) == 3:
                return result.model_copy(update={"commits_change": True})
            return result

    model = AllocationModel(
        [
            ("click", "Allocate stock", None),
            ("fill", "Warehouse", "North"),
            ("click", "Allocate", None),
            ("read", "Receipt", None),
        ]
    )
    with fixture_site(html) as url:
        monkeypatch.setattr(
            "interface_automation.page_workflow.simulator_url",
            lambda candidate: candidate.startswith(url),
        )
        result, cap = run_page(url, goal="Allocate 20 units to North", decider=model)
        assert result.status == "success" and cap is not None, result
        assert len(model.observations) == 4  # Two fields share one model decision.
        assert len(cap.inputs) == 2
        assert cap.inputs[0].type == "select"
        assert (
            cap.steps[-1].result_template
            == "Allocated {{input_quantity}} units to {{input_warehouse}}"
        )
        replay, _ = run_page(
            url, capability=cap, values={"input_quantity": "30", "input_warehouse": "South"}
        )
        assert replay.outputs == {"result": "Allocated 30 units to South"}
        cap.steps[-1].result_template = "Wrong receipt"
        bad, _ = run_page(
            url, capability=cap, values={"input_quantity": "30", "input_warehouse": "South"}
        )
        assert bad.code == "output_not_verified"


@pytest.mark.parametrize("html", ["<p>Loading</p>", "<button>Delete</button>"])
def test_no_usable_controls_stops_without_model_call(monkeypatch, html):
    monkeypatch.setattr("interface_automation.page_workflow.CONTROL_WAIT_SECONDS", 0.5)
    model = ScriptedDecider([])
    events = []
    with fixture_site(html) as url:
        result, cap = run_page(url, decider=model, events=events)
    assert result.code == "no_supported_controls" and cap is None
    assert model.observations == []
    assert len([e for e in events if e["event"] == "waiting_for_controls"]) == 1
    assert events[-1]["stage"] == "wait_for_controls"
    assert next(e for e in events if e["event"] == "page_observed")["offered_control_count"] == 0


def test_delayed_controls_are_reinspected_before_model_call():
    html = "<script>setTimeout(()=>{document.body.innerHTML='<output aria-label=\"Status\">Ready</output>'},900)</script>"
    model = ScriptedDecider([("read", "Status", None)])
    events = []
    with fixture_site(html) as url:
        result, cap = run_page(url, decider=model, events=events)
    assert result.status == "success" and cap is not None
    assert len(model.observations) == 1
    assert model.observations[0]["controls"][0]["name"] == "Status"
    assert any(e["event"] == "waiting_for_controls" for e in events)


def test_entry_dialog_navigation_replays_from_fresh_session():
    html = """<input readonly aria-label="Calendar"><button id="start" onclick="history.pushState({},'', '/accounts');this.hidden=true;welcome.hidden=false">GET STARTED NOW</button>
    <div role="dialog" aria-modal="true" id="welcome" hidden><h2>Welcome</h2><p>Feel free to explore!</p><button onclick="welcome.hidden=true;view.hidden=false">Ok</button></div>
    <button id="view" hidden onclick="history.pushState({},'', '/transfers');this.hidden=true;result.hidden=false">VIEW TRANSFERS</button>
    <h1 id="result" hidden>Upcoming Transfers</h1>"""
    model = ScriptedDecider(
        [
            ("click", "GET STARTED NOW", None),
            ("click", "Ok", None),
            ("click", "VIEW TRANSFERS", None),
            ("read", "Upcoming Transfers", None),
        ]
    )
    with fixture_site(html) as url:
        result, cap = run_page(url, goal="Read the transfers page heading", decider=model)
        assert result.outputs == {"result": "Upcoming Transfers"} and cap is not None
        assert not cap.inputs
        assert all(c["name"] != "Calendar" for o in model.observations for c in o["controls"])
        assert [s.page_path for s in cap.steps] == ["/", "/accounts", "/accounts", "/transfers"]
        assert cap.steps[0].destination_path == "/accounts"
        assert model.observations[-1]["page"]["path"] == "/transfers"
        replay, _ = run_page(url, capability=cap)
        assert replay.outputs == result.outputs


def test_confirmation_dialog_is_not_treated_as_welcome_navigation(monkeypatch):
    monkeypatch.setattr("interface_automation.page_workflow.CONTROL_WAIT_SECONDS", 0.2)
    html = '<button>Search</button><div role="dialog"><p>Welcome. Confirm transfer?</p><button>Ok</button></div>'
    model = ScriptedDecider([])
    with fixture_site(html) as url:
        result, _ = run_page(url, decider=model)
    assert result.code == "no_supported_controls" and not model.observations


def test_delayed_navigation_is_observed_and_wrong_replay_page_is_rejected(monkeypatch):
    html = """<button onclick="setTimeout(()=>{history.pushState({},'', '/destination');document.body.innerHTML='<h1>Destination</h1>'},900)">GET STARTED NOW</button>"""
    model = ScriptedDecider([("click", "GET STARTED NOW", None), ("read", "Destination", None)])
    with fixture_site(html) as url:
        result, cap = run_page(url, goal="Read Destination", decider=model)
        assert result.status == "success" and cap is not None
        assert cap.steps[0].destination_path == "/destination"
        assert model.observations[1]["page"]["path"] == "/destination"
        cap.steps[0].page_path = "/wrong-entry-page"
        monkeypatch.setattr("interface_automation.page_workflow.CONTROL_WAIT_SECONDS", 0.3)
        replay, _ = run_page(url, capability=cap)
        assert replay.code == "workflow_page_mismatch"


@pytest.mark.parametrize(
    "action,target,value,reason",
    [
        ("read", "c99", None, "target_not_observed"),
        ("read", "PRIVATE-VALUE", None, "target_not_observed"),
        ("fill", "c0", "PRIVATE-VALUE", "action_control_mismatch"),
        ("read", "c0", "PRIVATE-VALUE", "unexpected_value_for_action"),
        ("click", "c1", None, "target_not_offered"),
    ],
)
def test_decision_diagnostics_are_specific_and_do_not_record_values(action, target, value, reason):
    class InvalidDecider:
        def structured(self, instructions, observation, contract):
            return contract.model_validate({"action": action, "target": target, "value": value})

    events = []
    with fixture_site('<output aria-label="Status">Ready</output><button>Delete</button>') as url:
        result, cap = run_page(url, decider=InvalidDecider(), events=events)
    assert cap is None and result.observed == reason
    observation = next(e for e in events if e["event"] == "page_observed")
    assert observation["observed_control_count"] == 2
    assert observation["offered_control_count"] == 1
    proposal = next(e for e in events if e["event"] == "page_decision")
    assert proposal["action"] == action
    assert proposal["target"] == ("[invalid identifier]" if target == "PRIVATE-VALUE" else target)
    assert "PRIVATE-VALUE" not in json.dumps(events)
    assert not any(e["event"] == "action" for e in events)


@contextmanager
def fixture_site(html: str, status: int = 200) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class ScriptedDecider:
    """Offline model substitute: real inspection/execution/artifacts remain under test."""

    def __init__(self, actions: list[tuple[str, str, str | None]]):
        self.actions = iter(actions)
        self.observations: list[dict] = []

    def structured(self, instructions: str, observation: str, contract: type[T]) -> T:
        observed = json.loads(observation)
        if contract.__name__ == "GoalAssessment":
            return contract.model_validate({"outcome": "achieved", "requires_change": False})
        self.observations.append(observed)
        action, name, value = next(self.actions)
        control = next(c for c in observed["controls"] if c["name"] == name)
        return contract.model_validate({"action": action, "target": control["id"], "value": value})


PARCEL = """<!doctype html><label for="tracking">Parcel reference</label>
<input id="tracking" pattern="PK-[0-9]{3}" maxlength="6" required>
<label for="unused">Newsletter email</label><input id="unused" type="email">
<button onclick="result.hidden=false;result.textContent='In transit: '+tracking.value">Search</button>
<output id="result" aria-label="Delivery status" hidden></output>"""


def test_transfer_goal_cannot_be_completed_by_reading_transfers_heading():
    class TransferDecider(ScriptedDecider):
        def structured(self, instructions, observation, contract):
            if contract.__name__ == "GoalAssessment":
                observed = json.loads(observation)
                assert observed["goal"] == "Make a single transfer of $500 from checking to saving"
                assert observed["selected_result"] == "Upcoming Transfers"
                # Even an overly optimistic model cannot override the write boundary.
                return contract.model_validate({"outcome": "achieved", "requires_change": True})
            return super().structured(instructions, observation, contract)

    with fixture_site("<h1>Upcoming Transfers</h1>") as url:
        result, cap = run_page(
            url,
            goal="Make a single transfer of $500 from checking to saving",
            decider=TransferDecider([("read", "Upcoming Transfers", None)]),
        )
    assert result.code == "goal_requires_write_permission"
    assert cap is None and not result.outputs


def test_rejected_completion_continues_toward_original_goal():
    class CheckingDecider(ScriptedDecider):
        def structured(self, instructions, observation, contract):
            if contract.__name__ == "GoalAssessment":
                observed = json.loads(observation)
                return contract.model_validate(
                    {
                        "outcome": "achieved"
                        if observed["selected_result"] == "Delivered"
                        else "not_achieved",
                        "requires_change": False,
                    }
                )
            return super().structured(instructions, observation, contract)

    model = CheckingDecider([("read", "Shipments", None), ("read", "Status", None)])
    with fixture_site('<h1>Shipments</h1><output aria-label="Status">Delivered</output>') as url:
        result, cap = run_page(url, goal="Read the shipment status", decider=model)
        assert cap is not None
        replay, _ = run_page(url, capability=cap)
    assert result.outputs == {"result": "Delivered"} and cap is not None
    assert replay.outputs == result.outputs
    assert model.observations[-1]["rejected_completion_controls"] == ["Shipments"]


def test_unseen_field_schema_replay_and_unused_field() -> None:
    decider = ScriptedDecider(
        [
            ("fill", "Parcel reference", "PK-123"),
            ("click", "Search", None),
            ("read", "Delivery status", None),
        ]
    )
    with fixture_site(PARCEL) as url:
        result, cap = run_page(url, goal="Find delivery status for PK-123", decider=decider)
        assert result.status == "success"
        assert cap is not None
        assert [f.label for f in cap.inputs] == ["Parcel reference"]
        assert cap.inputs[0].pattern == "PK-[0-9]{3}"
        assert cap.inputs[0].maxLength == 6
        saved = cap.model_dump_json()
        assert "PK-123" not in saved and "In transit" not in saved
        replay, created = run_page(
            url,
            capability=PageCapability.model_validate_json(saved),
            values={cap.inputs[0].key: "PK-987"},
        )
        assert replay.outputs == {"result": "In transit: PK-987"}
        assert created is None
        invalid, _ = run_page(url, capability=cap, values={cap.inputs[0].key: "bad"})
        assert invalid.code == "invalid_workflow_input"
        mismatch, _ = run_page(url, capability=cap, values={"member_id": "12345"})
        assert mismatch.code == "workflow_inputs_mismatch"


def test_dynamic_second_page_input_and_select_are_inferred() -> None:
    html = """<label for="town">Destination city</label><input id="town" required>
    <button onclick="next.hidden=false;this.hidden=true">Search</button>
    <div id="next" hidden><label for="category">Room category</label>
    <select id="category"><option value="single">Single room</option><option value="double">Double room</option></select>
    <button onclick="result.hidden=false;result.textContent=town.value+' '+category.value">Find</button></div>
    <output id="result" aria-label="Available rooms" hidden></output>"""
    decider = ScriptedDecider(
        [
            ("fill", "Destination city", "Boston"),
            ("click", "Search", None),
            ("ask", "Room category", None),
            ("click", "Find", None),
            ("read", "Available rooms", None),
        ]
    )
    asked: list[FieldSpec] = []

    def answer(field: FieldSpec) -> str:
        asked.append(field)
        return "double"

    with fixture_site(html) as url:
        result, cap = run_page(url, goal="Find rooms in Boston", decider=decider, ask=answer)
        assert result.outputs == {"result": "Boston double"}
        assert cap is not None
        assert [f.label for f in cap.inputs] == ["Destination city", "Room category"]
        assert asked[0].type == "select"
        assert asked[0].options[1] == {"value": "double", "label": "Double room"}
        assert "Room category" not in str(decider.observations[0])
        replay, _ = run_page(
            url, capability=cap, values={cap.inputs[0].key: "Denver", cap.inputs[1].key: "single"}
        )
        assert replay.outputs == {"result": "Denver single"}


def test_model_invented_value_becomes_human_question() -> None:
    decider = ScriptedDecider(
        [
            ("fill", "Parcel reference", "PK-555"),
            ("click", "Search", None),
            ("read", "Delivery status", None),
        ]
    )
    with fixture_site(PARCEL) as url:
        result, cap = run_page(
            url, goal="Find my parcel", decider=decider, ask=lambda field: "PK-999"
        )
    assert result.outputs == {"result": "In transit: PK-999"}
    assert cap and "PK-999" not in cap.model_dump_json()


def test_non_demo_mutation_and_sensitive_fields_not_offered() -> None:
    html = '<input type="password" aria-label="Password"><button>Delete account</button><output aria-label="Status">Ready</output>'
    decider = ScriptedDecider([("read", "Status", None)])
    with fixture_site(html) as url:
        result, _ = run_page(url, goal="Read status", decider=decider)
    assert result.status == "success"
    offered = decider.observations[0]["controls"]
    assert [c["name"] for c in offered] == ["Status"]


@pytest.mark.parametrize(
    "script",
    [
        "fetch('/write',{method:'POST'}).catch(()=>{})",
        "new WebSocket('ws://'+location.host+'/socket')",
    ],
)
def test_read_only_network_policy_blocks_write_channels(script) -> None:
    html = f'<button onclick="{script};result.hidden=false">Search</button><output id="result" aria-label="Status" hidden>Changed</output>'
    with fixture_site(html) as url:
        result, cap = run_page(
            url, goal="Search", decider=ScriptedDecider([("click", "Search", None)])
        )
    assert result.code == "site_policy_blocked" and cap is None


def test_invalid_sample_can_be_corrected_without_another_model_call() -> None:
    decider = ScriptedDecider(
        [
            ("fill", "Parcel reference", "BAD"),
            ("click", "Search", None),
            ("read", "Delivery status", None),
        ]
    )
    questions = []

    def answer(field):
        questions.append(field)
        return "PK-123"

    with fixture_site(PARCEL) as url:
        result, cap = run_page(url, goal="Search BAD", decider=decider, ask=answer)
    assert result.status == "success" and cap is not None
    assert len(questions) == 1 and len(decider.observations) == 3


def test_blocked_background_resources_do_not_end_discovery() -> None:
    events = []
    html = '<img src="https://assets.invalid/private-name?token=SECRET"><script src="https://assets.invalid/script.js?key=SECRET"></script><output aria-label="Status">Ready</output>'
    with fixture_site(html) as url:
        result, cap = run_page(
            url,
            goal="Read status",
            decider=ScriptedDecider([("read", "Status", None)]),
            events=events,
        )
    assert result.status == "success" and cap is not None
    blocked = [e for e in events if e["event"] == "network_blocked"]
    assert blocked and all(not e["fatal"] for e in blocked)
    assert "SECRET" not in json.dumps(events) and "private-name" not in json.dumps(events)


def test_cross_origin_navigation_stops_with_specific_diagnostic() -> None:
    events = []
    with fixture_site(
        "<button onclick=\"location.href='https://other.invalid/private?secret=VALUE'\">Search</button>"
    ) as url:
        result, cap = run_page(
            url, goal="Search", decider=ScriptedDecider([("click", "Search", None)]), events=events
        )
    assert result.code == "site_policy_blocked" and cap is None
    assert result.observed == "cross_origin_navigation"
    assert events[-1]["stage"] == "execute_click"
    assert "VALUE" not in json.dumps(events)


@pytest.mark.parametrize("timeout", [True, False])
def test_loading_errors_log_stage_without_raw_error_data(monkeypatch, timeout) -> None:
    from playwright.sync_api import Error, Page, TimeoutError

    def broken_goto(*args, **kwargs):
        raise (TimeoutError if timeout else Error)(
            "net::ERR_NAME_NOT_RESOLVED https://private.example/SECRET?key=VALUE"
        )

    monkeypatch.setattr(Page, "goto", broken_goto)
    events = []
    with fixture_site("<p>Test</p>") as url:
        result, cap = run_page(url, events=events)
    assert cap is None
    assert result.code == ("page_timeout" if timeout else "browser_operation_failed")
    assert events[-1]["stage"] == "load_page"
    if not timeout:
        assert "ERR_NAME_NOT_RESOLVED" in result.observed
    assert "SECRET" not in json.dumps(events) and "VALUE" not in result.model_dump_json()


def test_artifact_binding_schema_tampering_is_rejected() -> None:
    with fixture_site(PARCEL) as url:
        _, cap = run_page(
            url,
            goal="Find PK-123",
            decider=ScriptedDecider(
                [
                    ("fill", "Parcel reference", "PK-123"),
                    ("click", "Search", None),
                    ("read", "Delivery status", None),
                ]
            ),
        )
    assert cap
    data = cap.model_dump()
    data["inputs"][0]["pattern"] = ".*"
    with pytest.raises(ValueError):
        PageCapability.model_validate(data)


def test_dashboard_question_save_and_schema_replay(tmp_path, monkeypatch) -> None:
    from interface_automation.dashboard import Dashboard, RunRequest

    model = ScriptedDecider(
        [
            ("ask", "Parcel reference", None),
            ("click", "Search", None),
            ("read", "Delivery status", None),
        ]
    )
    monkeypatch.setattr("interface_automation.dashboard.GeminiDecider", lambda *args: model)
    manager = Dashboard(tmp_path)

    def wait_for(predicate) -> None:
        deadline = time.monotonic() + 15
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert predicate(), manager.snapshot()

    with fixture_site(PARCEL) as url:
        run_id = manager.start(
            RunRequest(
                mode="discover",
                page_discovery=True,
                goal="Find my parcel",
                target_url=url,
                live=True,
            )
        )
        wait_for(lambda: manager.runs[run_id]["status"] == "needs_input")
        field = manager.runs[run_id]["input_fields"][0]
        assert field["label"] == "Parcel reference"
        with pytest.raises(ValueError):
            manager.answer_page(run_id, {"member_id": "12345"})
        manager.answer_page(run_id, {field["key"]: "PK-456"})
        wait_for(lambda: manager.active is None)
        assert manager.runs[run_id]["status"] == "success"
        assert not manager.workflows()
        manager.review(run_id, True)
        workflow = manager.snapshot()["workflows"][0]
        assert workflow["inputs"] == [field]
        replay_id = manager.start(
            RunRequest(mode="replay", workflow=workflow["id"], inputs={field["key"]: "PK-789"})
        )
        wait_for(lambda: manager.active is None)
        assert manager.runs[replay_id]["result"]["outputs"] == {"result": "In transit: PK-789"}
        for path in manager.directory.rglob("*.json*"):
            text = path.read_text()
            assert "PK-456" not in text and "PK-789" not in text


def test_http_error_is_reported_before_model_use():
    events = []
    with fixture_site("Access denied", status=403) as url:
        result, cap = run_page(url, events=events)
    assert result.code == "page_http_error" and result.observed == "HTTP 403"
    assert cap is None and events[-1]["stage"] == "load_page"


@pytest.mark.parametrize("failure", ["disappeared", "insufficient"])
def test_change_reobserves_result_without_resubmitting_and_replays_full_row(monkeypatch, failure):
    from interface_automation.page_workflow import PageRunner

    html = """<label>Destination<input id="destination"></label>
    <label>Quantity<input id="quantity" type="number"></label>
    <button onclick="window.commits=(window.commits||0)+1;formFields.hidden=true;receipt.hidden=false;row.innerHTML='<td>'+destination.value+'</td><td>'+quantity.value+'</td><td>'+window.commits+'</td>'">Save</button>
    <div id="formFields"></div><output aria-label="Notice">Saved</output>
    <table id="receipt" hidden><thead><tr><th>Destination</th><th>Quantity</th><th>Submissions</th></tr></thead><tbody><tr id="row"></tr></tbody></table>"""

    class Model(ScriptedDecider):
        checks = 0

        def structured(self, instructions, observation, contract):
            observed = json.loads(observation)
            if contract.__name__ == "GoalAssessment":
                self.checks += 1
                if failure == "insufficient" and self.checks == 1:
                    return contract.model_validate(
                        {"outcome": "not_achieved", "requires_change": True}
                    )
                assert "North" in observed["selected_result"]
                assert "20" in observed["selected_result"]
                return contract.model_validate({"outcome": "achieved", "requires_change": True})
            decision = super().structured(instructions, observation, contract)
            if decision.action == "click":
                decision.commits_change = True
            return decision

    original_act = PageRunner.act
    failed = False

    def act(runner, step, values):
        nonlocal failed
        if failure == "disappeared" and step.action == "read" and not failed:
            failed = True
            raise Stopped(Result(status="failure", code="page_control_changed"))
        return original_act(runner, step, values)

    monkeypatch.setattr(PageRunner, "act", act)
    model = Model(
        [
            ("fill", "Destination", "North"),
            ("fill", "Quantity", "20"),
            ("click", "Save", None),
            ("read", "Notice", None),
            ("read", "Result row", None),
        ]
    )
    events = []
    with fixture_site(html) as url:
        monkeypatch.setattr(
            "interface_automation.page_workflow.simulator_url",
            lambda candidate: candidate.startswith(url),
        )
        result, cap = run_page(url, goal="Allocate 20 to North", decider=model, events=events)
        assert result.status == "success" and cap is not None, result
        assert "North" in result.outputs["result"] and "20" in result.outputs["result"]
        assert cap.name.startswith("Apply change and verify")
        assert sum(step.action == "click" for step in cap.steps) == 1
        assert sum(step.action == "read" for step in cap.steps) == 1
        assert not any(event["event"] == "intervention" for event in events)
        replay, _ = run_page(
            url, capability=cap, values={"input_destination": "South", "input_quantity": "30"}
        )
        assert replay.status == "success", replay
        assert replay.outputs["result"].split() == ["South", "30", "1"]
