# Experimental page-derived workflows

Use the dashboard to try the generic engine. Use the synthetic-bank CLI to evaluate the reference implementation's contracts and recovery behavior.

## Page-derived inputs

You supply a goal and URL. Gemini selects actions from observed controls; the runner derives replay inputs and validation rules from the fields it fills. Later screens can add fields. A separate model assessment checks a proposed result against the original goal. The runner exposes complete table rows so the model can inspect related values together.

## Live run and its limits

`generic-assisted-discovery.jsonl` preserves the sanitized log from discovery `71646817082f4b8694823365fe5163ca`, started 2026-09-23 at 06:15:41 UTC. Gemini 3.5 Flash operated NGPF's synthetic bank simulator. The log omits sample input and returned values.

Gemini navigated the entry and welcome screens and opened Transfers. After a provider HTTP 503, the user took control of the same browser. The log records a click but omits its target and effect, so a reviewer cannot reconstruct that action. Automation resumed, filled frequency, source, destination, and amount, clicked Save, and read a result row. Gemini returned `achieved` with `requires_change=true`.

The runner then recorded `capability_not_saved` with `unrecorded_human_repair`. No artifact exists for this run. The log supports a claim of assisted execution and model-assessed completion; it provides neither transfer replay evidence nor an independent verification of simulator state.

## Local browser tests

In `tests/test_page_workflow.py`, scripted model responses drive real local browser pages. The tests cover unrelated forms, dependent choices, batched fills, changed-input replay, result rows, and bounded result refreshes without resubmission. They check the runner against known fixtures. Testing live model interpretation requires separate provider runs.

## Scope decision

I kept the generic engine and used the narrower reference path for the assignment demonstration. Increasing a timeout cannot reconstruct a manual repair or define a missing output contract. Generic handoff records event kinds, suppresses artifacts after intervention, and offers no replay takeover. Exact selectors and receipt templates can break; richer redacted failure evidence and reusable business outcomes remain unfinished.

Before adding sites, I would address repair recording, resume checks, output/checkpoint contracts, and failure evidence. REPORT describes the proposed surface and tenant abstractions. Those designs still require implementation and validation.
