# Infrastructure and design choices

| Component | Choice | Trade-off |
| --- | --- | --- |
| Runtime | Python 3.12 with pinned dependencies | Compact implementation; Windows source-checkout installation is the supported path. |
| Browser | Playwright Chromium | Browser actions and same-session human access; desktop support requires another adapter. |
| Interface | Standard-library local web dashboard and CLI | No hosted service or frontend build pipeline; not a production HTTP stack. |
| Execution | One dashboard worker at a time | Simple ownership and quota management; no distributed scheduling. |
| Model | Gemini 2.5 Flash, free tier | Paced structured-action requests; provider access and quota depend on the user account. |
| Storage | JSON capabilities and sanitized JSONL events | Reviewable local files; no multi-tenant storage isolation. |
| Target | Bundled synthetic bank and limited page-derived workflows | External targets use restricted same-origin search/navigation; broad public-site compatibility is not established. |

Supply a Gemini key as `AI_API_KEY` and consent to API usage before discovery. The dashboard defaults to Gemini 2.5 Flash with thinking disabled for short action decisions. Replay needs no provider account. Reserve limits apply across provider adapters; they do not measure charges or enable billing.

Choose an optional model through the CLI. The application has no provider fallback or dashboard provider selector. Adding a provider requires an adapter and compatibility checks. See [provider setup](../README.md#bring-your-own-api-key) for key names, model choices, and validation status.
