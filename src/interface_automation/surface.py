"""Shared browser action boundary and live operator ownership."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from playwright.sync_api import Error, Page, Route

from .policy import Policy
from .schema import Inputs, RecoveryRule, Result, Step

STEPS = {
    "fill_member": Step(action="fill", role="textbox", name="Member ID", parameter="member_id"),
    "search": Step(action="click", role="button", name="Search"),
    "open_accounts": Step(action="click", role="link", name="View accounts"),
    "read_balance": Step(action="read", role="status", name="Savings balance", output="balance"),
}
SCENARIOS = ("normal", "slow", "permission_denied", "session_expired", "manual_review")
CHECKPOINT = "Account details loaded"


def permitted(url: str, base_url: str) -> bool:
    try:
        target, base = urlsplit(url), urlsplit(base_url)
        return (
            target.scheme == base.scheme == "http"
            and target.hostname == base.hostname == "127.0.0.1"
            and target.port == base.port
            and target.path in ("", "/")
            and target.username is None
            and target.password is None
        )
    except ValueError:
        return False


class Stopped(Exception):
    def __init__(self, result: Result):
        self.result = result


class Surface:
    def __init__(
        self,
        page: Page,
        base_url: str,
        inputs: Inputs,
        policy: Policy | None = None,
        events: list[dict[str, object]] | None = None,
    ):
        self.page, self.base_url, self.inputs = page, base_url, inputs
        self.owner: Literal["automation", "human"] = "automation"
        self.events: list[dict[str, object]] = events if events is not None else []
        self.outputs: dict[str, str] = {}
        self.learned: list[RecoveryRule] = []
        self.recordable = True
        self.policy = policy or Policy()
        page.set_default_timeout(3000)
        page.context.route("**/*", self.guard)

    def guard(self, route: Route) -> None:
        if self.permits_url(route.request.url) and route.request.method == "GET":
            route.continue_()
        else:
            route.abort()

    def open(self, scenario: str) -> None:
        if not self.permits_url(self.base_url) or scenario not in SCENARIOS:
            raise Stopped(Result(status="failure", code="target_blocked"))
        self.page.goto(f"{self.base_url}/?scenario={scenario}")

    def permits_url(self, url: str) -> bool:
        return permitted(url, self.base_url) and self.policy.permits_url(url)

    def observe(self) -> str:
        # Fixed vocabulary observed from the synthetic UI; no account values or names.
        visible = [
            key
            for key, step in STEPS.items()
            if self.page.get_by_role(step.role, name=step.name, exact=True).is_visible()
            and self.page.get_by_role(step.role, name=step.name, exact=True).is_enabled()
        ]
        filled = (
            self.page.get_by_role("textbox", name="Member ID", exact=True).input_value()
            == self.inputs.member_id
        )
        checkpoint = self.page.get_by_text(CHECKPOINT, exact=True).is_visible()
        # Availability reflects the UI and policy, not our preferred workflow order.
        # Re-entering the input or searching again remains a real model choice.
        available: list[str] = [
            action for action in visible if action in self.policy.allowed_actions
        ]
        if checkpoint and "balance" in self.outputs:
            available.append("finish")
        return json.dumps(
            {
                "visible_controls": visible,
                "available_actions": available,
                "member_input_present": bool(
                    self.page.get_by_role("textbox", name="Member ID", exact=True).input_value()
                ),
                "member_input_matches_parameter": filled,
                "balance_extracted": "balance" in self.outputs,
                "checkpoint_visible": checkpoint,
            }
        )

    def act(self, step: Step) -> None:
        if self.owner != "automation":
            raise Stopped(Result(status="failure", code="human_owns_session"))
        if not self.permits_url(self.page.url):
            raise Stopped(Result(status="failure", code="target_blocked"))
        if not any(step == STEPS[name] for name in self.policy.allowed_actions):
            raise Stopped(Result(status="failure", code="action_blocked"))
        target = self.page.get_by_role(step.role, name=step.name, exact=True)
        if step.action == "fill":
            target.fill(self.inputs.member_id)
        elif step.action == "click":
            target.click()
            if step.name == "Search":
                self.page.get_by_text(
                    re.compile(
                        r"^(View accounts|Member not found|Permission denied|Session expired|Operator review required)$"
                    )
                ).wait_for()
                for text, code in (
                    ("Member not found", "member_not_found"),
                    ("Permission denied", "permission_denied"),
                    ("Session expired", "session_expired"),
                ):
                    if self.page.get_by_text(text, exact=True).is_visible():
                        raise Stopped(
                            Result(
                                status="business_outcome"
                                if code == "member_not_found"
                                else "failure",
                                code=code,
                                expected="Member search result",
                                observed=text,
                            )
                        )
        else:
            value = target.inner_text().strip()
            if not re.fullmatch(r"[0-9]+\.[0-9]{2}", value):
                raise Stopped(Result(status="failure", code="output_invalid"))
            self.outputs["balance"] = value
        self.events.append({"event": "action", "action": step.action, "control": step.name})

    def needs_review(self) -> bool:
        return self.page.get_by_text("Operator review required", exact=True).is_visible()

    def failure_evidence(self, path: Path | None) -> None:
        if path is None:
            return
        # Scope: our bundled synthetic page only. Mask all data-bearing regions.
        # Unknown pages are never captured; no unmasked fallback is permitted.
        try:
            if not permitted(self.page.url, self.base_url):
                raise ValueError("Unexpected page")
            self.page.get_by_role("heading", name="Sample Credit Union", exact=True).wait_for()
            snapshot = self.page.screenshot(
                mask=[self.page.locator("input, textarea, table, small, header")],
                mask_color="#303840",
                full_page=True,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(snapshot)
            self.events.append(
                {"event": "failure_screenshot", "redaction": "synthetic_data_regions_masked"}
            )
        except (Error, OSError, ValueError):
            self.events.append({"event": "failure_screenshot_unavailable"})

    def recover(
        self,
        reason: str,
        headed: bool,
        operator: Callable[[Page], None] | None,
        step: int,
        mode: Literal["discovery", "replay"],
    ) -> None:
        if not self.permits_url(self.page.url):
            raise Stopped(Result(status="failure", code="target_blocked"))
        if not headed and operator is None:
            raise Stopped(
                Result(
                    status="failure",
                    code="operator_required",
                    observed=f"Human assistance required: {reason}",
                )
            )
        self.handoff(operator, step=step, mode=mode, reason=reason)

    def restored_state(self) -> str | None:
        if not self.permits_url(self.page.url) or self.needs_review():
            return None
        if (
            self.page.get_by_role("textbox", name="Member ID", exact=True).input_value()
            != self.inputs.member_id
        ):
            return None
        if self.page.locator("#content").get_attribute("data-member") != self.inputs.member_id:
            return None
        if self.page.get_by_text(CHECKPOINT, exact=True).is_visible():
            return "details"
        if self.page.get_by_role("link", name="View accounts", exact=True).is_visible():
            return "results"
        return None

    def satisfied(self, action: Step) -> bool:
        if not any(action == STEPS[name] for name in self.policy.allowed_actions):
            raise Stopped(Result(status="failure", code="action_blocked"))
        state = self.restored_state()
        return (action == STEPS["search"] and state in {"results", "details"}) or (
            action == STEPS["open_accounts"] and state == "details"
        )

    def handoff(
        self,
        operator: Callable[[Page], None] | None = None,
        *,
        step: int = 0,
        mode: Literal["discovery", "replay"] = "replay",
        reason: str = "operator_review",
    ) -> None:
        """operator injects test interactions; normal runs wait for real human input."""
        self.owner = "human"
        self.events.append(
            {
                "event": "intervention",
                "reason": reason,
                "owner": "human",
                "operator_mode": "simulated" if operator else "manual",
                "capability": "savings_balance",
                "step": step,
                "mode": mode,
                "state": "Resolve the blocked lookup and leave results or account details for the original member",
            }
        )
        self.page.evaluate(
            """context => {
            window.operatorEvents=[]; window.resumeRequested=false;
            window.captureOperator = e => {
              const el=e.target.closest('button,input,a'); if(!el)return;
              const label=el.tagName==='INPUT'?(el.name==='member'?'Member ID':'other'):el.textContent.trim();
              const allowed=['Member ID','Search','View accounts','Continue review','Restore session','Resume automation'];
              window.operatorEvents.push({event:e.type,control:allowed.includes(label)?label:'other'});
            };
            document.addEventListener('click',window.captureOperator,true);
            document.addEventListener('input',window.captureOperator,true);
            const panel=document.createElement('aside'); panel.id='operator-handoff';
            panel.style='position:fixed;bottom:0;left:0;right:0;padding:20px;background:#ffd980;z-index:9999';
            panel.textContent=`Savings balance lookup (${context.mode}), step ${context.step}. ` +
              `Automation paused: ${context.reason}. ` +
              'You control this session. Restore member results or account details, then resume. ';
            const button=document.createElement('button');button.textContent='Resume automation';
            button.onclick=()=>window.resumeRequested=true;panel.append(button);document.body.append(panel);
        }""",
            {"step": step, "mode": mode, "reason": reason.replace("_", " ")},
        )
        try:
            if operator:
                operator(self.page)
            self.page.wait_for_function("window.resumeRequested === true", timeout=120_000)
            captured = self.page.evaluate("window.operatorEvents")
            for entry in captured if isinstance(captured, list) else []:
                if isinstance(entry, dict) and entry.get("event") in {"click", "input"}:
                    control = entry.get("control")
                    if control in {
                        "Member ID",
                        "Search",
                        "View accounts",
                        "Continue review",
                        "Restore session",
                        "Resume automation",
                        "other",
                    }:
                        self.events.append(
                            {"event": "human_action", "kind": entry["event"], "control": control}
                        )
            if self.restored_state() is None:
                raise Stopped(Result(status="failure", code="resume_state_invalid"))
            entries = captured if isinstance(captured, list) else []
            controls = [entry.get("control") for entry in entries if isinstance(entry, dict)]
            if "other" in controls:
                self.recordable = False
            fixes = {
                "operator_review": ("Continue review", "continue_review"),
                "session_expired": ("Restore session", "restore_session"),
            }
            if reason in fixes and fixes[reason][0] in controls:
                rule = RecoveryRule.model_validate({"trigger": reason, "action": fixes[reason][1]})
                if rule not in self.learned:
                    self.learned.append(rule)
                self.events.append({"event": "recovery_learned", **rule.model_dump()})
            elif reason in fixes:
                self.recordable = False
            self.outputs.clear()
            self.owner = "automation"
            self.events.append({"event": "resumed", "owner": "automation"})
        finally:
            self.page.evaluate("""() => {
              document.removeEventListener('click',window.captureOperator,true);
              document.removeEventListener('input',window.captureOperator,true);
              document.querySelector('#operator-handoff')?.remove();
            }""")

    def apply_recovery(self, reason: str, rules: list[RecoveryRule]) -> bool:
        expected = {
            "operator_review": ("continue_review", "Continue review"),
            "session_expired": ("restore_session", "Restore session"),
        }
        if reason not in expected:
            return False
        action, label = expected[reason]
        if not any(rule.trigger == reason and rule.action == action for rule in rules):
            return False
        if not self.permits_url(self.page.url) or self.owner != "automation":
            raise Stopped(Result(status="failure", code="target_blocked"))
        if "search" not in self.policy.allowed_actions:
            raise Stopped(Result(status="failure", code="action_blocked"))
        self.page.get_by_role("button", name=label, exact=True).click()
        self.page.get_by_role("link", name="View accounts", exact=True).wait_for()
        if self.restored_state() != "results":
            raise Stopped(Result(status="failure", code="resume_state_invalid"))
        self.events.append({"event": "recovery_replayed", "trigger": reason, "action": action})
        return True

    def finish(self, checkpoint: str = CHECKPOINT) -> Result:
        self.page.get_by_text(checkpoint, exact=True).wait_for()
        if "balance" not in self.outputs:
            raise Stopped(Result(status="failure", code="output_missing"))
        return Result(status="success", code="completed", outputs=self.outputs.copy())
