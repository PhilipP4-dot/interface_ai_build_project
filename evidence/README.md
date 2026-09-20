# MVP demonstration evidence

These files provide reviewable proof of real discovery, model-free replay, and learned human recovery. They are optional demonstration material, not application dependencies or a chronological development journal.

Tests exercise current code with offline model substitutes. These recordings show what the real integration did during particular past runs. They do not validate every later change. Dated filenames preserve provenance; successful and failed outcomes are labeled explicitly.

## Included demonstration set

These six files form a compact demonstration suitable for a portfolio or assignment review:

| File | What it demonstrates |
| --- | --- |
| [Discovery log](gemini-discovery-2026-09-18-retry.jsonl) | Four real Gemini 2.5 Flash decisions completing the browser lookup, with multiple available actions. |
| [Discovered capability](gemini-capability-2026-09-18-retry.json) | The reusable, parameterized workflow emitted by successful discovery. |
| [Replay log](gemini-replay-2026-09-18.jsonl) | Successful execution for another sample member without model calls. |
| [Human-assisted discovery](human-assisted-discovery-2026-09-19.jsonl) | Discovery with an operator resolving a review interruption. |
| [Human-assisted capability](human-assisted-capability-2026-09-19.json) | A version 1.1 workflow explicitly recording human-assisted provenance and a conditional recovery rule. |
| [Learned recovery replay](learned-recovery-replay-2026-09-19.jsonl) | Reuse of the saved recovery without another human intervention or model call. |

Capabilities are executable examples; logs are supporting records. Retain each capability's accompanying log when making claims about how it was discovered. Do not relabel hand-authored or recovered artifacts as ordinary successful discovery.

## Handling and limits

Recorded action logs omit member input values and returned balances. Screenshot masking is specific to the synthetic demo. Do not add credentials, raw provider responses, or real customer data. Keep routine experiments and runtime output in ignored `runs/`.

Removing this folder does not prevent installation or execution. It removes the evidence capabilities from the dashboard's examples and requires updating the README's evidence-based CLI command and any other references. The hand-authored fixture in `artifacts/` remains available. Historical files are preserved as recorded rather than rewritten to match newer behavior.
