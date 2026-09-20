# Requirements coverage

This checklist maps the local prototype to the supplied Computer-Use Automation System assignment. It describes implementation scope, not authorization to publish or submit.

| Requirement | Implementation |
| --- | --- |
| Goal and target | Natural-language savings goal and explicit synthetic-bank app entry point. |
| Real discovery | Gemini 2.5 Flash selects actions against a live Chromium page; step, wait, quota, and no-progress bounds apply. |
| Reusable capability | Typed/versioned JSON with parameter references, accessible targets, outputs, and checkpoint. Human-assisted discovery does not silently emit incomplete capabilities. |
| Model-free replay | Validates outcomes, extracts balance, and verifies completion without model decisions. |
| Runtime errors | Business not-found, bounded waits, automatic intervention for supported recoverable blocks, and hard policy/permission stops. |
| Safety | Restrictive target/action policy, safe observations, sanitized logs, and fixture-specific screenshot masks. |
| Human control | Same-session pause, contextual intervention, recorded control names, explicit resume, and identity/state verification. |
| Heterogeneity | REPORT.md explains surface adapters and tenant/version compatibility as future design extensions. |
| Deliverables | README setup/demo, seven-heading REPORT, tests, and indexed genuine discovery/replay/manual evidence. |

Limitations include one fixed action catalog, synthetic data, recognized results/details resume states, no global watchdog, and no remote operator console. The Markdown report's exact rendered page count depends on export settings. Public repository hosting and submission are external steps.
