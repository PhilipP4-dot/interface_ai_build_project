"""Recheck the genuine discovered demo artifact without model calls.

The handoff case uses a scripted operator on the real browser. It is not evidence
of a new human or LLM discovery. Use a new output directory on each invocation.
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import Page

from interface_automation.demo import serve
from interface_automation.replay import replay
from interface_automation.schema import Capability, Inputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    artifact = root / "evidence/gemini-capability-2026-09-18-retry.json"
    args.output.mkdir(parents=True, exist_ok=False)
    checks = []

    def operator(page: Page) -> None:
        # The populated member field proves this is the existing session.
        assert page.get_by_role("textbox").input_value() == "67890"
        page.get_by_role("button", name="Continue review", exact=True).click()
        page.get_by_role("button", name="Resume automation", exact=True).click()

    with serve() as url:
        for name, member, scenario, status, code in [
            ("changed-input", "67890", "normal", "success", "completed"),
            ("not-found", "99999", "normal", "business_outcome", "member_not_found"),
            ("permission-denied", "67890", "permission_denied", "failure", "permission_denied"),
            ("same-session-handoff", "67890", "manual_review", "success", "completed"),
        ]:
            capability = Capability.model_validate_json(artifact.read_text(encoding="utf-8"))
            events: list[dict[str, object]] = []
            screenshot = args.output / "permission-denied.png" if status == "failure" else None
            result = replay(
                capability,
                Inputs(member_id=member),
                url,
                scenario,
                operator=operator if name == "same-session-handoff" else None,
                events=events,
                failure_screenshot=screenshot,
            )
            passed = result.status == status and result.code == code
            if status == "success":
                passed = passed and result.outputs == {"balance": "842.10"}
            if screenshot:
                passed = passed and screenshot.exists()
            if name == "same-session-handoff":
                kinds = [e["event"] for e in events]
                passed = passed and all(
                    k in kinds for k in ["intervention", "human_action", "resumed"]
                )
                if passed:
                    passed = (
                        kinds.index("intervention")
                        < kinds.index("human_action")
                        < kinds.index("resumed")
                    )
            passed = passed and not any(e["event"] == "api_response" for e in events)
            events.append({"event": "result", **result.model_dump(exclude={"outputs"})})
            serialized = "\n".join(json.dumps(e) for e in events) + "\n"
            # Only known synthetic data is checked; this is not a general PII scanner.
            if any(value in serialized for value in ["67890", "99999", "842.10"]):
                raise RuntimeError("Synthetic invocation data leaked into evidence")
            (args.output / f"{name}.jsonl").write_text(serialized, encoding="utf-8")
            checks.append(
                {"case": name, "passed": passed, "status": result.status, "code": result.code}
            )
    report = {
        "artifact": artifact.relative_to(root).as_posix(),
        "discovery": "Historical genuine Gemini discovery; not rerun by this script",
        "execution": "Current local browser replay; no model adapter instantiated",
        "operator": "Scripted operator callback for the handoff case, not a human recording",
        "outputs": "Synthetic outputs asserted in memory, omitted from saved evidence",
        "checks": checks,
    }
    (args.output / "acceptance.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if all(c["passed"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
