"""Bounded observe/decide/act discovery; model selection is outside the executor."""

import json
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Literal, Protocol

from playwright.sync_api import Error, Page, sync_playwright

from .policy import Policy
from .schema import Capability, Contract, Inputs, Result, Step
from .surface import CHECKPOINT, Stopped, Surface


class Decision(Contract):
    action: Literal[
        "fill_member",
        "search",
        "open_accounts",
        "read_balance",
        "fill_balance",
        "update_balance",
        "finish",
    ]


class Decider(Protocol):
    provenance: Literal["llm_discovery", "offline_test"]

    def decide(self, goal: str, observation: str) -> Decision: ...


def discover(
    goal: str,
    inputs: Inputs,
    base_url: str,
    decider: Decider,
    scenario: str = "normal",
    headed: bool = False,
    max_steps: int = 10,
    operator: Callable[[Page], None] | None = None,
    events: list[dict[str, object]] | None = None,
    failure_screenshot: Path | None = None,
    policy: Policy | None = None,
    pause_request: Event | None = None,
    action_delay: float = 0,
) -> tuple[Result, Capability | None]:
    steps: list[Step] = []
    recent_actions: list[str] = []
    previous_observation: str | None = None
    unchanged_count = 0
    index = 0
    recoveries = 0
    assisted = False
    if not 1 <= max_steps <= 10 or len(goal) > 500:
        return Result(status="failure", code="discovery_limits_invalid").with_details(), None
    with sync_playwright() as driver:
        try:
            browser = driver.chromium.launch(headless=not headed)
        except Error:
            return Result(status="failure", code="browser_unavailable").with_details(), None
        surface: Surface | None = None
        try:
            context = browser.new_context(service_workers="block", accept_downloads=False)
            surface = Surface(context.new_page(), base_url, inputs, policy, events)
            surface.open(scenario)
            for index in range(1, max_steps + 1):
                if pause_request is not None and pause_request.wait(action_delay):
                    pause_request.clear()
                    if recoveries >= 2:
                        raise Stopped(Result(status="failure", code="intervention_limit"))
                    surface.recover("manual_takeover", headed, operator, index, "discovery")
                    recoveries += 1
                    assisted = True
                    previous_observation = None
                observation = surface.observe()
                unchanged_count = unchanged_count + 1 if observation == previous_observation else 0
                if unchanged_count >= 2:
                    if not headed and operator is None:
                        raise Stopped(
                            Result(
                                status="failure",
                                code="no_progress",
                                expected="A changed UI state",
                                observed="Repeated unchanged state",
                            )
                        )
                    if recoveries >= 2:
                        raise Stopped(Result(status="failure", code="intervention_limit"))
                    surface.recover("no_progress", headed, operator, index, "discovery")
                    recoveries += 1
                    assisted = True
                    unchanged_count = 0
                    observation = surface.observe()
                previous_observation = observation
                state = json.loads(observation)
                state["recent_actions"] = recent_actions[-5:]
                observation = json.dumps(state)
                decision = decider.decide(goal, observation)
                if pause_request is not None and pause_request.is_set():
                    # A pending model response must not act on a page the human will change.
                    continue
                recent_actions.append(decision.action)
                surface.events.append(
                    {"event": "decision", "action": decision.action, "observation": observation}
                )
                if decision.action == "finish":
                    result = surface.finish()
                    if result.status != "success" or not steps:
                        return result, None
                    if assisted and not surface.recordable:
                        surface.events.append(
                            {"event": "capability_not_saved", "reason": "human_assisted_discovery"}
                        )
                        return result, None
                    capability = Capability(
                        schema_version="1.2"
                        if surface.updating
                        else ("1.1" if assisted else "1.0"),
                        name="update_savings_balance" if surface.updating else "savings_balance",
                        provenance="human_assisted_discovery"
                        if assisted and decider.provenance != "offline_test"
                        else decider.provenance,
                        input_type="member_id: five-digit string; new_balance: USD decimal string"
                        if surface.updating
                        else "member_id: five-digit string",
                        output_type="balance: USD decimal string",
                        steps=list(surface.catalog.values()) if assisted else steps,
                        recoveries=surface.learned,
                        checkpoint=CHECKPOINT,
                    )
                    return result, capability
                if decision.action not in surface.catalog:
                    raise Stopped(Result(status="failure", code="action_blocked"))
                step = surface.catalog[decision.action].model_copy()
                try:
                    surface.act(step)
                except (Error, Stopped) as blocked:
                    if isinstance(blocked, Stopped) and blocked.result.code != "session_expired":
                        raise
                    if recoveries >= 2:
                        raise Stopped(Result(status="failure", code="intervention_limit")) from None
                    reason = "session_expired" if isinstance(blocked, Stopped) else "ui_unavailable"
                    surface.recover(reason, headed, operator, index, "discovery")
                    recoveries += 1
                    assisted = True
                    previous_observation = None
                    continue
                steps.append(step)
                # The declared output and checkpoint are deterministic facts. Do not
                # spend another model request asking it to certify those facts.
                if "balance" in surface.outputs:
                    result = surface.finish()
                    if result.status == "success":
                        if assisted and not surface.recordable:
                            surface.events.append(
                                {
                                    "event": "capability_not_saved",
                                    "reason": "human_assisted_discovery",
                                }
                            )
                            return result, None
                        return result, Capability(
                            schema_version="1.2"
                            if surface.updating
                            else ("1.1" if assisted else "1.0"),
                            name="update_savings_balance"
                            if surface.updating
                            else "savings_balance",
                            provenance="human_assisted_discovery"
                            if assisted and decider.provenance != "offline_test"
                            else decider.provenance,
                            input_type="member_id: five-digit string; new_balance: USD decimal string"
                            if surface.updating
                            else "member_id: five-digit string",
                            output_type="balance: USD decimal string",
                            steps=list(surface.catalog.values()) if assisted else steps,
                            recoveries=surface.learned,
                            checkpoint=CHECKPOINT,
                        )
                if surface.needs_review():
                    if recoveries >= 2:
                        raise Stopped(Result(status="failure", code="intervention_limit"))
                    surface.recover("operator_review", headed, operator, index, "discovery")
                    recoveries += 1
                    assisted = True
            raise Stopped(Result(status="failure", code="step_limit"))
        except Stopped as exc:
            if surface is not None and exc.result.status == "failure":
                surface.failure_evidence(failure_screenshot)
            return exc.result.with_details(index), None
        except Error:
            if surface is not None:
                surface.failure_evidence(failure_screenshot)
            return Result(
                status="failure",
                code="ui_failure",
                step=index,
                expected="Available control and verified checkpoint",
                observed="Control unavailable, ambiguous, or timed out",
            ), None
        except (ValueError, RuntimeError, OSError):
            # Do not expose provider error bodies, prompts, credentials, or goal text.
            if surface is not None:
                surface.failure_evidence(failure_screenshot)
            return Result(
                status="failure",
                code="model_or_budget_failure",
                step=index,
                expected="Valid model decision within budget",
                observed="Decision or budget validation failed",
            ), None
        finally:
            browser.close()
