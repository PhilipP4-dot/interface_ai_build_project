# Workflow Studio

Use Workflow Studio to discover a browser workflow with an LLM, save its steps and parameter bindings, and replay it without model calls. The project includes a synthetic-bank reference workflow and an experimental engine for page-derived workflows.

## Submission scope

**Start with the synthetic-bank CLI demonstration below.** You can inspect its input/output contracts, replay it for another member, test business outcomes and permission failures, and take over the same browser session. The evidence folder includes real Gemini discovery logs and masked failure evidence.

The dashboard's **Create a workflow** path uses the experimental engine. You supply a goal and URL; discovery derives replay inputs from the controls it fills. Generic replay handoff, manual-repair capture, and output contracts remain incomplete. An assisted discovery can complete the goal without saving a workflow. Read the [design report](REPORT.md) and [generic extension evidence](evidence/generic-extension.md) for the scope and remaining work.

## Install and start

Supported setup: Windows, Python 3.12, and a source checkout.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m interface_automation dashboard
```

Open [Workflow Studio](http://127.0.0.1:8766). Installation and replay require no API key. For live discovery, copy `.env.example` to `.env` and supply your Gemini `AI_API_KEY`. The ignored local file takes precedence over the process environment. Keep `.env` out of commits.

## Assignment demonstration

Replay the saved Gemini-discovered artifact and run the acceptance cases without an API key:

```powershell
.\.venv\Scripts\python.exe -m interface_automation replay --artifact evidence/gemini-capability-2026-09-18-retry.json --member-id 67890
.\.venv\Scripts\python.exe scripts/verify_submission.py --output runs/submission-check
```

The acceptance script checks changed-input replay, not-found, permission denial, and same-session handoff. It uses a scripted operator and makes no model calls. Choose a new output directory for each run. Inspect the saved results in the [acceptance report](evidence/reference-acceptance/acceptance.json).

To run a new discovery, configure your Gemini key and use unused output filenames. The CLI starts the synthetic target:

```powershell
.\.venv\Scripts\python.exe -m interface_automation discover --target synthetic-bank --model gemini-2.5-flash --goal "Read the member's savings balance" --member-id 12345 --live --headed --output runs/submission-capability.json --events runs/submission-discovery.jsonl
.\.venv\Scripts\python.exe -m interface_automation replay --artifact runs/submission-capability.json --member-id 67890 --events runs/submission-replay.jsonl
```

To take over the browser during replay, run:

```powershell
.\.venv\Scripts\python.exe -m interface_automation replay --artifact evidence/gemini-capability-2026-09-18-retry.json --member-id 67890 --scenario manual_review --headed --events runs/submission-handoff.jsonl --updated-artifact runs/submission-recovered.json
```

At the pause, click **Continue review**, then **Resume automation** in the same browser within two minutes. Replay checks the member and page state before continuing. Inspect the learned recovery in `runs/submission-recovered.json`.

## Bring your own API key

Supply your own provider account and key for discovery. **Use `AI_API_KEY` for Gemini and `OPENAI_API_KEY` for OpenAI.** Replay and offline tests need no key.

| Provider / configured model | Key setting | Where it works | Validation status |
| --- | --- | --- | --- |
| Gemini / `gemini-2.5-flash` | `AI_API_KEY` | Dashboard and CLI (default) | Historical demo lookup evidence, offline browser tests, and a live read-only NGPF navigation check |
| Gemini / `gemini-3.5-flash` | `AI_API_KEY` | Optional CLI/adapter model | Structured-response tests and an assisted live generic run; no transfer replay claim |
| OpenAI / `gpt-5.4` | `OPENAI_API_KEY` | CLI with `--model gpt-5.4` | Adapter and offline tests; no successful live end-to-end evidence included |
| Gemini / `gemini-2.0-flash` | `AI_API_KEY` | Legacy CLI option only | Earlier live attempt returned NOT_FOUND; account access is not guaranteed |
| Other providers or models | Not configured | Requires an adapter or compatibility work | Requires code changes |

Copy `.env.example` to `.env`, then set **only the key you intend to use**. Leave unused entries commented out. You can also set the matching process environment variable. A key present in `.env` overrides the environment; a blank active entry is an error. Choose the provider with the configured model; the application has no provider fallback.

For the existing OpenAI CLI adapter, set `OPENAI_API_KEY` and run from the project directory with unused output paths:

```powershell
.\.venv\Scripts\python.exe -m interface_automation discover --model gpt-5.4 --goal "Read the member's savings balance" --member-id 12345 --live --headed --output artifacts/openai-discovered.json --events runs/openai-discovery.jsonl
```

Check that your account has access and quota for the chosen model. The dashboard defaults to Gemini 2.5 Flash; `--model` selects the CLI provider. Find the shared default in `DEFAULT_GEMINI_MODEL` in `src/interface_automation/gemini.py`. The 2.5 adapter disables thinking for short decisions; 3.5 uses low thinking effort. OpenAI has no automatic retry or Gemini pacing. Both adapters use the reservation limits described below.

To support another provider, implement `structured(instructions, observation, contract)` for page discovery (or `decide(goal, observation)` returning a validated `Decision` for the legacy demo engine) and wire its key, model selection, response validation, quota handling, and tests into the application. Adding another provider requires code changes; the dashboard has no provider selector.

## Run a workflow

Select a saved workflow to generate its required input fields. Nothing is selected initially; switching workflows clears previous inputs. Use **Rename workflow** to give a saved workflow a recognizable name. Names persist locally in ignored dashboard storage. The included lookup accepts five-digit member IDs: `12345` and `67890` have accounts; `99999` returns a normal not-found outcome.

For page workflows, replay uses the saved URL, inputs, control bindings, and page checks. A bundled-demo workflow can use the dashboard's demo instance after a restart. Other page workflows keep their recorded target.

Watch execution in the separate automation browser. You can read outputs until the dashboard restarts; local history retains progress and outcome metadata. The reference engine also supports masked failure screenshots and learned recovery rules.

## Create a workflow

1. Select **Create a workflow** and describe your goal, including sample values you already know. For example: **Read 12345's savings balance**.
2. Enter a website URL under **Website and demo settings**, or leave it blank for the bundled demo. Use a URL without credentials, query parameters, or fragments.
3. Allow Gemini to receive the goal and page control metadata. Discovery inspects visible controls at each step and selects relevant fields. A missing value becomes a question using that field's label, type, constraints, and options.
4. Review the resulting draft and confirm which inputs should be requested on every replay. Save or discard it before restarting the dashboard.

Gemini chooses actions from observed controls. The runner derives validation rules and bindings from each field it fills, including fields on later screens. Each filled field becomes a replay input. You review that schema before saving; you cannot yet mark fields as constants. Replay asks for fresh values rather than using the discovery samples as defaults.

New workflows use schema 2.0 and run through the dashboard. The CLI and schema 1.x examples retain the specialized demo engine. Existing saved workflows continue to replay.

## Human input and stopping

Page discovery asks in the dashboard when a selected field lacks a usable sample value. Questions time out after five minutes; **Cancel** ends that attempt. **Pause and take control** hands over at the next execution boundary. Recoverable discovery failures also trigger handoff, with five minutes to resume or stop in the same browser. Policy violations remain hard stops. Generic manual repairs are not compiled into replay steps, so assisted runs do not produce saved workflows.

In the reference engine, you can take over for review screens, expired sessions, UI errors, or repeated unchanged states. You can also request **Pause and take control**. Resolve the problem in the automation browser and click **Resume automation** within two minutes. Identity and page-state checks must pass. Supported review/session repairs are saved as conditional recovery rules; unsupported actions prevent recording a repair. These recovery rules remain specific to schema 1.x demo workflows.

## Edit the demo balance manually

Search for a valid member, open **View accounts**, enter **New savings balance (USD)**, then select **Update savings balance**. Amounts must be between 0 and 999999999.99 with at most two decimal places.

Changes persist across refreshes in that browser tab using session storage. Separate automation browser contexts start with the original synthetic balances. You can also run the **Balance update** example with member ID and new balance inputs. Updates run without a confirmation prompt, as configured for this synthetic demo. Read the changed balance in the automation result. Your separate demo tab and future runs keep their own balances.

## CLI balance updates

Use the hand-authored update example to change a synthetic balance and verify its read-back:

```powershell
.\.venv\Scripts\python.exe -m interface_automation replay --artifact artifacts/update_savings_balance.json --member-id 12345 --new-balance 500.00
```

For CLI update discovery, add `--new-balance 500.00` and an update goal to the discovery command above. `--policy configs/read-only.json` blocks writes. The dashboard also accepts goals such as **Set member 12345's savings balance to 500.00** through its experimental page engine.

The CLI accepts schema 1.x and saves discovery artifacts without dashboard draft review. Use the dashboard for schema 2.0. Run `--help` for scenario, policy, and evidence options. Exit codes: 0 for success or a business outcome, 1 for execution failure, and 2 for invalid arguments or configuration.

## Limits and data handling

| Boundary | Behavior |
| --- | --- |
| Generic controls | Up to 35 visible controls per state: text/number/email/date fields, native selects, buttons, links, and result text. The allowed simulator also supports standard ARIA dropdowns. |
| Generic discovery | Up to eight seconds to find usable controls; review after 20 steps; at most two five-minute handoffs and 60 iterations in the headed dashboard. Saved schema 2.0 artifacts allow at most 20 steps. |
| Provider usage | Gemini requests have 15-second spacing and bounded retries. Each attempt reserves $0.10, capped at $1 per run and $20 total. These reservations do not measure billing or remaining provider quota. |
| Site policy | Synthetic changes on the bundled demo and NGPF `/bank-sim/`; limited search/navigation elsewhere. Server write requests and WebSockets remain blocked. |
| Network policy | Same-origin GET/HEAD traffic. Cross-origin background reads are blocked and logged; cross-origin navigation stops execution. Some sites need the blocked assets or POST requests. |
| Session storage | One active dashboard run. History and saved workflows live in ignored `runs/dashboard/`. Active sessions, questions, and unapproved drafts are lost on restart. |

For simulator changes, discovery checks the selected result against the original goal and records a result template for replay. It can inspect a disappearing or insufficient result twice more without repeating submission. Review drafts and test different inputs: model assessment can be wrong, and exact templates can fail when receipt formatting changes. Existing artifacts keep their recorded checks. An uncertain write must not trigger a blind retry.

Use synthetic data. Gemini receives goals, control metadata, result snippets, and supplied inputs during completion assessment. Logs omit input/output values as separate fields, but page labels, selectors, routes, and receipt text can contain sensitive information. Inspect artifacts before sharing. The reference screenshot mask covers the known demo; the generic engine has no failure screenshot capture. Neither network restrictions nor screenshot masks provide a production security sandbox.

Frames, shadow DOM, uploads, checkboxes, authentication, and arbitrary visual interfaces are outside the implemented scope. GET requests and client scripts can have side effects. Keep tests within trusted pages. Preserve the budget ledger; deleting it removes the cumulative spending guard. See [REPORT.md](REPORT.md) for the recovery and safety design.

## Verification and design

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m mypy src
```

Tests use local browsers, simulated operators, and offline model substitutes. They consume no Gemini quota. See the [design report](REPORT.md), [evidence guide](evidence/README.md), [requirements coverage](docs/requirements.md), [infrastructure choices](docs/infrastructure.md), and [installation verification](docs/installation-verification.md). Historical live evidence is separate from current regression tests.

## Examples and evidence

Use `artifacts/` for hand-authored examples and `evidence/` for the assignment demonstration. Keep the evidence folder in your submission. It contains original live-provider runs, current reference acceptance cases, and a generic-extension run with its limitations documented in the [evidence guide](evidence/README.md).

Tests use scripted model responses and operators. Live logs establish behavior for the recorded model and run; they do not validate later changes. Keep routine experiments in ignored `runs/`.
