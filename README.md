# Workflow Studio

A local computer-use automation MVP for a synthetic banking website. Gemini discovers a savings lookup through browser actions; a saved, parameterized workflow replays without model calls. The dashboard connects creation, replay, human review, results, and history.

## Install and start

Supported setup: Windows, Python 3.12, and a source checkout.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m interface_automation dashboard
```

Open [Workflow Studio](http://127.0.0.1:8766). Installation and replay require no API key. For live discovery, copy `.env.example` to `.env` and supply your Gemini `AI_API_KEY`. The ignored local file takes precedence over the process environment. Never commit credentials.

## Bring your own API key

Someone cloning this project uses their own provider account and key. **Keys are provider-specific: `AI_API_KEY` is the Gemini key setting, not a universal key setting.** Replay and offline tests need no key.

| Provider / configured model | Key setting | Where it works | Validation status |
| --- | --- | --- | --- |
| Gemini / `gemini-2.5-flash` | `AI_API_KEY` | Dashboard and CLI (default) | Live discovery evidence and offline tests |
| OpenAI / `gpt-5.4` | `OPENAI_API_KEY` | CLI with `--model gpt-5.4` | Adapter and offline tests; no successful live end-to-end evidence included |
| Gemini / `gemini-2.0-flash` | `AI_API_KEY` | Legacy CLI option only | Earlier live attempt returned NOT_FOUND; use 2.5 for the demonstrated setup |
| Other providers or models | Not configured | Requires an adapter or compatibility work | Not supported by simply changing the key |

Copy `.env.example` to `.env`, then set **only the key you intend to use**. Leave unused entries commented out. Alternatively, set the matching process environment variable. A key present in `.env` overrides the environment; a blank active entry is an error. Keys are never automatically switched between providers.

For the existing OpenAI CLI adapter, set `OPENAI_API_KEY` and run from the project directory with unused output paths:

```powershell
.\.venv\Scripts\python.exe -m interface_automation discover --model gpt-5.4 --goal "Read the member's savings balance" --member-id 12345 --live --headed --output artifacts/openai-discovered.json --events runs/openai-discovery.jsonl
```

Your account must have API access to the selected model and sufficient provider quota. The configured model names are a code allowlist, not a guarantee of current availability for every account. OpenAI CLI requests have no automatic retry or Gemini pacing. Both adapters use the same internal reservation ledger; reservations do not measure provider charges. Selecting OpenAI does not make the dashboard use it: dashboard creation remains fixed to Gemini 2.5 Flash. A successfully saved capability can be replayed without the original provider or its key.

To support another provider, implement the discovery decider contract (`decide(goal, observation)` returning a validated `Decision`) and wire its key, model selection, response validation, quota handling, and tests into the application. There is currently no configurable generic API endpoint or dashboard provider selector.

## Run a workflow

Select a saved workflow to generate its required input fields. Nothing is selected initially; switching workflows clears previous inputs. Use **Rename workflow** to give a saved workflow a recognizable name. Names persist locally in ignored dashboard storage. The included lookup accepts five-digit member IDs: `12345` and `67890` have accounts; `99999` returns a normal not-found outcome.

Expand **Demo settings**, then click **Use demo site** to select the dashboard's bundled demo, or paste a running local demo URL such as `http://127.0.0.1:8765`. A blank URL starts a fresh demo for the run. Only an unchanged copy of the bundled page is accepted, not arbitrary websites. `localhost` is normalized to loopback.

A separate automation browser opens. The dashboard shows progress, results, masked failure screenshots, event downloads, and completed-run history.

## Create a workflow

Describe a savings lookup, for example **Read 12345's savings balance**, and explicitly allow Gemini quota use. A clearly recognized member number is used directly; missing or ambiguous numbers trigger a question. Recognition is a small rule-based parser, not general natural-language understanding.

Gemini selects among four supported actions: fill the member ID, search, open accounts, and read the balance. Successful goal-first discovery produces a draft. Review the inputs, steps, output, and learned recoveries, then **Confirm and save workflow** or discard it. The example member number is not embedded in the saved workflow. Drafts and unanswered questions are held in memory and are lost on restart.

## Human review

Review screens, expired sessions, action-time UI errors, and repeated unchanged discovery states can request assistance. You can also choose **Pause and take control**. A pending pause waits for the current action or API request to finish.

In the automation browser, resolve the issue, leave the original member's results or account details visible, and click **Resume automation** within two minutes. The engine verifies the target, member identity, and recognized state before continuing. Each run permits at most two interventions. Permission denial and policy violations stop; not-found is a business outcome.

Supported review/session fixes are saved as conditional recovery rules. Unsupported human actions prevent saving a repair. Replay can save a new version without overwriting its source. **Demo conditions** injects test scenarios; runtime detection triggers the intervention.

## Edit the demo balance manually

Search for a valid member, open **View accounts**, enter **New savings balance (USD)**, then select **Update savings balance**. Amounts must be between 0 and 999999999.99 with at most two decimal places.

Changes persist across refreshes in that browser tab using session storage. Separate automation browser contexts start with the original synthetic balances. Automated discovery and replay remain read-only; there is no balance-update workflow.

## CLI

Replay a genuine discovered capability without API access:

```powershell
.\.venv\Scripts\python.exe -m interface_automation replay --artifact evidence/gemini-capability-2026-09-18-retry.json --member-id 67890
```

Discover and replay a new workflow, using unused output filenames:

```powershell
.\.venv\Scripts\python.exe -m interface_automation discover --goal "Read the member's savings balance" --member-id 12345 --live --headed --output artifacts/discovered.json --events runs/discovery.jsonl
.\.venv\Scripts\python.exe -m interface_automation replay --artifact artifacts/discovered.json --member-id 67890 --events runs/replay.jsonl
```

CLI discovery saves directly; it does not use the dashboard's draft review. The default replay artifact is a hand-authored fixture. Options include `--scenario`, `--policy configs/read-only.json`, `--failure-screenshot`, and replay's `--updated-artifact`. Use `--help` for details. Exit codes: 0 success/business outcome, 1 execution failure, 2 invalid arguments/configuration.

## Limits and data handling

- One local application, one lookup capability, and one active dashboard run. Generated forms do not imply arbitrary-site discovery or new action support.
- Gemini 2.5 Flash is the dashboard default. Calls are spaced at least 15 seconds apart with bounded retries, ten decisions, and a no-progress check. Remaining account-wide quota is unknown; avoid concurrent CLI/API traffic.
- The ledger reserves $0.10 per attempt, capped at $1 per run and $20 cumulatively. These are internal guards, not measured bills. Do not delete the ledger to reset spending.
- Loopback host/origin/token checks protect the local dashboard. It is not an authenticated remote or multi-user service. Policy can narrow allowed actions, not authorize transactions.
- Only synthetic goals should be sent to Gemini. Goals may contain the sample member number. Observations and persisted events omit typed values and returned balances. Screenshot masks are demo-specific.
- Completed history and dashboard workflows live in ignored `runs/dashboard/`. They are not included in a push. Active sessions cannot resume after shutdown, and there is no global watchdog or general cancel-running-run control.
- Credentials, budgets, caches, browser state, and runtime output are excluded by `.gitignore`. The documented deployment is a source checkout, not a standalone wheel service.

## Verification and design

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src
```

Tests use local browsers, simulated operators, and offline model substitutes. They consume no Gemini quota. See the [design report](REPORT.md), [evidence guide](evidence/README.md), [requirements coverage](docs/requirements.md), [infrastructure choices](docs/infrastructure.md), and [installation verification](docs/installation-verification.md). Historical live evidence is separate from current regression tests.

## Examples and evidence

`artifacts/` contains reusable workflow examples. `evidence/` contains a curated demonstration of real discovery, model-free replay, and human-assisted recovery. Evidence is optional for running the application; it supports review of the MVP, rather than serving as a development diary.

Automated tests check current behavior using offline model substitutes. Live evidence records what happened in specific past runs and shows that the real provider integration worked at that time. It does not establish that every later version or model still works. Dates in filenames identify provenance, not release versions.

The repository includes one discovery log and its generated capability, one replay log, and the human-assisted discovery/capability/recovery replay set. The [evidence guide](evidence/README.md) indexes these six files. Routine experiments and runtime logs belong in ignored `runs/`.

If publishing without evidence, update commands and documentation that reference it. The application can still replay `artifacts/savings_balance.json`, the hand-authored fixture, without any evidence files or API key:

```powershell
.\.venv\Scripts\python.exe -m interface_automation replay --artifact artifacts/savings_balance.json --member-id 67890
```

Removing evidence capabilities also removes those examples from the dashboard's saved-workflow list; it does not remove locally saved workflows.
