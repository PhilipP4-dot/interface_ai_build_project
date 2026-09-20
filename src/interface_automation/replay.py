"""Model-free execution using the shared browser policy boundary."""

from collections.abc import Callable
from pathlib import Path
from threading import Event

from playwright.sync_api import Error, Page, sync_playwright

from .policy import Policy
from .schema import Capability, Inputs, Result
from .surface import Stopped, Surface, permitted  # noqa: F401 - compatibility export


def replay(
    capability: Capability,
    inputs: Inputs,
    base_url: str,
    scenario: str = "normal",
    headed: bool = False,
    operator: Callable[[Page], None] | None = None,
    events: list[dict[str, object]] | None = None,
    failure_screenshot: Path | None = None,
    policy: Policy | None = None,
    pause_request: Event | None = None,
    action_delay: float = 0,
) -> Result:
    index = 0
    with sync_playwright() as driver:
        try:
            browser = driver.chromium.launch(headless=not headed)
        except Error:
            return Result(status="failure", code="browser_unavailable").with_details()
        surface: Surface | None = None
        try:
            context = browser.new_context(service_workers="block", accept_downloads=False)
            surface = Surface(context.new_page(), base_url, inputs, policy, events)
            surface.open(scenario)
            recoveries = 0
            reconciled = False
            for index, step in enumerate(capability.steps, 1):
                if pause_request is not None and pause_request.wait(action_delay):
                    pause_request.clear()
                    if recoveries >= 2:
                        raise Stopped(Result(status="failure", code="intervention_limit"))
                    surface.recover("manual_takeover", headed, operator, index, "replay")
                    recoveries += 1
                    reconciled = True
                if reconciled and surface.satisfied(step):
                    surface.events.append(
                        {"event": "step_verified", "step": index, "control": step.name}
                    )
                    continue
                try:
                    surface.act(step)
                    reason = "operator_review" if surface.needs_review() else None
                except Stopped as blocked:
                    if blocked.result.code != "session_expired":
                        raise
                    reason = "session_expired"
                except Error:
                    reason = "ui_unavailable"
                if reason:
                    if recoveries >= 2:
                        raise Stopped(Result(status="failure", code="intervention_limit"))
                    recoveries += 1
                    if not surface.apply_recovery(reason, capability.recoveries):
                        surface.recover(reason, headed, operator, index, "replay")
                    reconciled = True
                    if not surface.satisfied(step):
                        # Reissue only a read or parameter fill; never blindly repeat a click.
                        if step.action == "click":
                            raise Stopped(Result(status="failure", code="resume_state_invalid"))
                        surface.act(step)
            result = surface.finish(capability.checkpoint)
            if surface.recordable and surface.learned:
                for rule in surface.learned:
                    if rule not in capability.recoveries:
                        capability.recoveries.append(rule)
                capability.schema_version = "1.1"
                surface.events.append(
                    {"event": "capability_updated", "reason": "verified_human_recovery"}
                )
            return result
        except Stopped as exc:
            if surface is not None and exc.result.status == "failure":
                surface.failure_evidence(failure_screenshot)
            return exc.result.with_details(index)
        except Error:
            if surface is not None:
                surface.failure_evidence(failure_screenshot)
            return Result(
                status="failure",
                code="ui_failure",
                step=index,
                expected="Available control and verified checkpoint",
                observed="Control unavailable, ambiguous, or timed out",
            )
        finally:
            browser.close()
