# Design report

## Architecture

I chose a synthetic-bank lookup as the reference workflow: supply a natural-language goal and member ID, run LLM discovery, save a capability, then replay it for another member. The local target lets a reviewer reproduce not-found outcomes, permission failures, expired sessions, and human review without financial data. The evidence folder includes original live-provider logs and current offline acceptance results.

I used Python, Pydantic, and Playwright to keep the implementation in one process. In `discovery.py`, the model selects an action from the controls available on the current page. The `Surface` adapter validates and executes it. In `replay.py`, the executor follows the saved artifact without model calls. The demo adapter supplies a banking action catalog and interprets known states; the model chooses the next action. This is constrained discovery, with no model training or fine-tuning.

Use the CLI for the reference demonstration. The dashboard also runs `page_workflow.py`, an experimental engine that derives inputs from page controls. I kept separate schema dispatch because the two engines have different contracts and recovery support. One worker owns the dashboard browser; HTTP handlers exchange questions and resume signals with that worker. Gemini 2.5 Flash is the default. Replay needs no provider account.

## Artifact schema

I separated invocation values from recorded steps so a caller can reuse a capability with new inputs. Strict Pydantic models reject unknown fields and inconsistent bindings. Schema 1.x declares provenance, named input/output contracts, fill/click/read steps, parameter references, accessible role/name targets, and a checkpoint. Version 1.1 adds conditional review/session recovery; 1.2 supports synthetic balance updates. Member IDs and balances use validated string representations.

The artifact stores the execution contract outside the model transcript. A reviewer can inspect its targets, inputs, and checks without interpreting a conversation. Versioned schemas let the executor reject unsupported contracts instead of guessing their meaning.

Experimental schema 2.0 adds page-derived field constraints, selectors, page paths, and result templates. Each filled field becomes a replay parameter; users cannot yet mark constants. Its outputs remain string maps with a descriptive label. Users must save dashboard drafts before restarting because drafts live in memory. The CLI accepts 1.x; the dashboard also accepts 2.0.

## Determinism & error handling

I use exact accessible roles/names, bounded waits, member identity checks, and a visible checkpoint for reference replay. Missing or ambiguous controls stop execution or require an operator. Determinism refers to execution rules: the application can return a different balance or deny access on a later run.

Callers receive a `Result` with success and outputs, a business outcome such as `member_not_found`, or a failure with code, step, expected, and observed fields. A missing member is a valid lookup result. Known review/session conditions permit a saved recovery or human handoff. Permission denial stops the run.

After takeover, the executor checks which steps the operator completed. It can reissue a parameter fill or read but does not repeat an uncertain click. Synthetic updates require confirmation and a matching balance read-back. A timeout after Save does not prove the write failed.

For generic discovery, I added a separate model assessment against the original goal and deterministic receipt templates for replay. Model assessment can still misjudge success. Structural selectors and exact templates can break across layout or receipt changes. After a marked simulator submission, the runner permits result inspection and at most two result refreshes within the run limits. Generic business-outcome classification and replay recovery remain incomplete.

## Heterogeneity & multi-tenant

I separated `Surface` from orchestration, but the current contracts still contain browser and banking assumptions. To add desktop or legacy-web support, I would define a versioned adapter with observe, resolve, act, checkpoint, and handoff operations. Target bindings would distinguish DOM/accessibility controls, desktop accessibility controls, and visual anchors. Adapter implementers would own targeting, waits, ambiguity checks, and redaction. Visual targeting would need confidence thresholds and escalation; I have not implemented that fallback or frame support.

For tenant reuse, I would store product/version, capability revision, semantic contracts, and adapter requirements in a shared vendor package. Administrators would configure approved base URLs, credential references, and narrow locator overrides per tenant. Compatibility checks would compare screen signatures and checkpoints before execution. An incompatible version would require review and regression replay rather than a silent shared-artifact update. Operators would trace runs by tenant and capability revision, with separate browser contexts and access-controlled storage. These are proposed extensions; the current fixed-URL artifacts provide no cross-tenant reuse guarantee.

## Escalation & handoff

In the reference engine, an operator can take over for review, an expired session, unavailable controls, no progress, or a requested pause. The intervention log includes capability, step, reason, mode, and state guidance. The operator uses the same browser and clicks Resume automation. During the pause, automation cedes control and records recognized control names and event kinds without typed values.

I bounded handoff to two interventions and two minutes per intervention. Before resuming, the executor verifies the original member and a supported page state. It can save recognized review/session repairs as conditional rules. Tests use scripted operators; the historical evidence includes a manual discovery handoff.

Generic discovery asks for missing values and permits two five-minute handoffs. It records event kinds without enough detail to reconstruct manual repairs, so an assisted run produces no artifact. Generic replay stops on failure without equivalent takeover. A user can therefore complete a goal yet have no workflow to replay.

## Safety

For the reference engine, callers can configure a host/path/action allowlist within the demo boundary. Read-only policy blocks synthetic updates. The runner rejects unsupported actions and invalid resume states. Generic policy permits synthetic changes on the bundled demo and the exact NGPF simulator scope, with restricted navigation/search elsewhere. GET requests and client scripts can still cause side effects; these restrictions do not isolate a production transaction system.

I limited reference logs to known controls and state flags, omitting member values, balances, credentials, and raw provider errors. Failure screenshots mask the known demo's data-bearing regions. The capture code provides no unmasked fallback. Generic labels, selectors, routes, and fixed receipt text can contain sensitive data, and generic failure snapshots are absent. Use synthetic data and inspect artifacts before sharing.

Developers supply keys outside Git. Internal reservations cap attempts at $1 per run and $20 total; they do not measure billing. The prototype lacks a global watchdog and production isolation.

## Cuts

I retained the generic engine to demonstrate page-derived inputs and observed-control planning. In the recorded NGPF run, Gemini reached Save and assessed a result row after a provider-error handoff. The runner saved no capability because it could not reconstruct the manual action. That run demonstrates assisted execution; it does not demonstrate transfer replay. Local tests cover unrelated forms and changed-input replay with scripted decisions.

I bounded further site coverage to focus on output contracts, manual repair recording, replay handoff, and redacted failure evidence. Desktop execution, tenant infrastructure, authenticated sites, frames/shadow DOM, arbitrary widgets, durable drafts, and a remote console remain outside scope. The reference demonstration gives reviewers a reproducible route through discovery, replay, outcomes, and handoff. The generic extension documents the work still needed to provide that coverage on other applications.
