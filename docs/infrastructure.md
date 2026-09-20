# Infrastructure and design choices

| Component | Choice | Trade-off |
| --- | --- | --- |
| Runtime | Python 3.12 with pinned dependencies | Compact implementation; Windows source-checkout installation is the supported path. |
| Browser | Playwright Chromium | Real UI actions and same-session human access; not desktop automation. |
| Interface | Standard-library local web dashboard and CLI | No hosted service or frontend build pipeline; not a production HTTP stack. |
| Execution | One dashboard worker at a time | Simple ownership and quota management; no distributed scheduling. |
| Model | Gemini 2.5 Flash, free tier | Genuine structured-action discovery with paced requests; account-wide quota is not observable. |
| Storage | JSON capabilities and sanitized JSONL events | Reviewable local files; no multi-tenant storage isolation. |
| Target | Bundled synthetic bank | Exercises search, details, extraction, and exceptional states without real financial data. |

API consent is explicit. Budget reservations are internal guards, not actual charges. Replay needs no provider account. Live discovery requires the selected provider's API access and quota; this project does not activate billing, deploy services, or publish anything. The retained OpenAI and Gemini 2.0 CLI options are not automatic fallbacks; the supported demonstration uses Gemini 2.5 Flash.

Cloners supply their own credentials. Gemini uses `AI_API_KEY`; the optional OpenAI CLI adapter uses `OPENAI_API_KEY` and `--model gpt-5.4`. The dashboard does not have a provider selector. Arbitrary keys, models, and compatible-looking API endpoints are not automatically supported. See [provider setup and validation status](../README.md#bring-your-own-api-key).
