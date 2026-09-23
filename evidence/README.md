# MVP demonstration evidence

Keep this folder in the assignment submission. Start with the live discovery artifact and its replay log, then inspect the current acceptance cases and the generic-extension limitation.

Use the original logs to verify the model, actions, and outcome of each recorded run. Use regression tests to check later code changes. Dates identify the source runs.

## Included demonstration set

Inspect these six files for the original live discovery, replay, and manual recovery:

| File | What it demonstrates |
| --- | --- |
| [Discovery log](gemini-discovery-2026-09-18-retry.jsonl) | Four real Gemini 2.5 Flash decisions completing the browser lookup, with multiple available actions. |
| [Discovered capability](gemini-capability-2026-09-18-retry.json) | The reusable, parameterized workflow emitted by successful discovery. |
| [Replay log](gemini-replay-2026-09-18.jsonl) | Successful execution for another sample member without model calls. |
| [Human-assisted discovery](human-assisted-discovery-2026-09-19.jsonl) | Discovery with an operator resolving a review interruption. |
| [Human-assisted capability](human-assisted-capability-2026-09-19.json) | A version 1.1 workflow with human-assisted provenance and a conditional recovery rule. |
| [Learned recovery replay](learned-recovery-replay-2026-09-19.jsonl) | Reuse of the saved recovery without another human intervention or model call. |

Keep each capability with its discovery log. Preserve its provenance: hand-authored, model-discovered, and human-assisted artifacts support different claims.

## Current reference acceptance

[`reference-acceptance/acceptance.json`](reference-acceptance/acceptance.json) records four checks of the original genuine discovered capability against the current demo engine:

- [Changed-input replay](reference-acceptance/changed-input.jsonl): declared synthetic balance checked in memory; no model calls.
- [Not found](reference-acceptance/not-found.jsonl): a `business_outcome`, not an execution failure.
- [Permission denial](reference-acceptance/permission-denied.jsonl): structured failure and a [masked screenshot](reference-acceptance/permission-denied.png).
- [Same-session handoff](reference-acceptance/same-session-handoff.jsonl): a **scripted operator** resolves review in the original browser and resumes. For a human-operated recording, use the original discovery evidence above.

Reproduce these cases with `.\.venv\Scripts\python.exe scripts/verify_submission.py --output runs/submission-check`, choosing a new output directory. The script runs without a model adapter. It checks outputs in memory and omits their values from saved logs.

## Experimental generic extension

Read [the scope assessment](generic-extension.md) with [the assisted NGPF discovery log](generic-assisted-discovery.jsonl). Gemini assessed completion, but the runner produced no reusable artifact after human intervention. There is no transfer replay evidence for that run.

## Handling and limits

Recorded action logs omit member input values and returned balances. Screenshot masking is specific to the synthetic demo. Do not add credentials, raw provider responses, or real customer data. Keep routine experiments in ignored `runs/`. Preserve original logs and artifacts when documenting newer behavior. You can run the application without this folder, but removing it also removes its example capabilities from the dashboard and breaks the evidence-based demo commands.
