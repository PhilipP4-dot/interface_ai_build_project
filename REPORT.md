# Design report

## Architecture

Workflow Studio connects a local dashboard to a Python browser-automation engine. A loopback HTTP server presents workflow creation, replay, progress, results, intervention instructions, and history. One worker owns each browser session, and the dashboard admits one run at a time. Playwright drives a bundled synthetic bank in a separate Chromium window. This keeps deployment small and makes the same session directly accessible to a human; it avoids a remote-browser service and its authentication and streaming complexity.

Discovery observes a safe vocabulary of visible controls and state, asks Gemini 2.5 Flash to select an action, and executes it through the shared Surface boundary. Visible policy-permitted alternatives remain available; recent actions supply context without forcing a sequence. The target is explicitly `synthetic-bank`. This is a constrained savings-balance demonstration, not an arbitrary-goal agent. Replay consumes a saved capability without invoking a model. CLI and dashboard use the same engines. Dashboard goal-first creation uses rule-based member-number recognition, requests missing information, and presents a successful discovery as an in-memory draft for confirmation. Replay fields are derived from saved step parameters and validation metadata; this does not expand the fixed action catalog.

## Artifact schema

Strict Pydantic models validate schema versions 1.0 and 1.1, provenance, input/output descriptions, ordered steps, and a success checkpoint. Each action names an accessible role and exact control label. A five-digit member number is supplied per invocation; the artifact records a parameter reference rather than the original number. The declared output is a USD decimal balance string, validated during extraction.

Artifacts are separate from provider transcripts. Provenance distinguishes hand-authored fixtures, offline tests, genuine discovery, and explicitly recovered historical recordings. Successful assisted discovery normalizes verified navigation into the fixed lookup sequence and uses explicit human-assisted provenance. Version 1.1 adds conditional recovery rules for the synthetic review and expired-session controls. Repeated clicks are not copied into the normal path. Unsupported human controls prevent recording a repair. Successful replay can emit a new version; original files remain intact. These rules are specific to safe synthetic controls, not authorization to repeat real approvals or credentials. The current narrow schema favors reviewability over generality.

## Determinism & error handling

Replay uses exact role/name targeting, bounded waits, output validation, and the account-details checkpoint. Missing or ambiguous controls cannot silently count as success. Member-not-found is a business outcome. Permission denial, policy violations, malformed output, and provider failures stop with structured diagnostics. Slow UI responses receive bounded waits rather than open-ended retries.

Review interstitials, expired sessions, and action-time UI errors request assistance in a visible session. Repeated unchanged discovery states also escalate. There are at most two interventions, ten discovery decisions, bounded provider requests, and a two-minute wait per handoff. There is no independent overall watchdog. No model is called during replay recovery. After human work, replay verifies recognized completed steps instead of blindly repeating clicks; remaining reads still validate their outputs. Unknown state or changed identity fails closed.

Final events include status, code, step, expectation, and observation but omit returned balances. Failure screenshots mask recognized synthetic data regions and are never overwritten. A missing final output follows the failure-evidence path. Startup failures cannot provide a screenshot of a page that never opened.

## Heterogeneity & multi-tenant

Surface separates observation, execution, verification, and ownership from the saved workflow. Extending to legacy web requires versioned control mappings, frame awareness, and reviewed fallback targeting. A desktop implementation needs a distinct accessibility or visual adapter with window identity and post-action checks. Those adapters are design extensions, not implemented features.

Tenant reuse should separate semantic workflow steps from reviewed tenant host/control mappings and permissions. Artifacts should declare compatible adapter/application versions. A mismatched screen should fail preconditions and route review rather than silently changing targets. Tenant credentials, browser profiles, evidence stores, and retention rules would require isolation. The present single-user local process deliberately avoids provisioning that infrastructure.

## Escalation & handoff

The dashboard also supports voluntary takeover of a healthy run. Its pause endpoint sets a thread-safe request consumed at an execution boundary; the HTTP thread never drives Playwright directly. A current provider call is allowed to finish, and its decision is discarded if a pause is pending. Dashboard runs provide a two-second interval between steps. Manual takeover uses the same identity checks, resume reconciliation, and intervention bound as automatic escalation.

Intervention is triggered by detected runtime conditions, not by a user-defined review workflow. The demo's optional scenarios inject those conditions for testing. The system cedes ownership of the same browser session, publishes the capability, mode, step, and safe reason/state context, and exposes explicit Resume automation control. Dashboard events show that human attention is needed. Control names are recorded without typed values. Unknown inputs, including the manual balance editor, are classified as unsupported rather than learned as member entry.

The human may clear a review, restore the sample session, or advance to account details. Resume requires the allowed origin, unchanged member input, matching result identity, and either the results or details screen. Outputs are cleared so automation reads fresh values. This reconciliation is specific to the synthetic app; it does not claim arbitrary navigation recovery. Policy denial is never converted into an opportunity to bypass policy. Headless callers without an operator receive a structured stop.

## Safety

Only the four supported actions and exact local demo origin are permitted. JSON policy can narrow that boundary, not authorize transactions or external sites. Browser contexts block service workers and downloads. Dashboard endpoints check loopback host, origin, and a per-session token; this is local access protection, not production operator authentication.

Keys remain in ignored local configuration. Goal text is sent to the provider but not persisted in logs; users must use synthetic goals. Observations and durable histories omit member values and account outputs. Returned balances are displayed only in dashboard memory or CLI output. Screenshots use fixture-specific masks, not universal sensitive-data detection.

Gemini calls are paced with bounded rate-limit retries and a stop on recognized daily exhaustion. The application cannot observe other clients' account usage. Its permanent $0.10-per-attempt reservations enforce $1/run and $20 cumulative guards; these are not billing measurements. Free-tier use and explicit API consent remain the default dashboard workflow.

## Cuts

The project demonstrates real multi-choice discovery, parameterized model-free replay, expected exceptional outcomes, and same-session manual handoff. Automated tests use simulated operators and offline model doubles; real-provider and earlier manual evidence are separately identified. Installation is verified in a separate Windows/Python environment with cached browser/download files.

Cuts include arbitrary-site discovery, general visual targeting, production tenants, remote co-browsing, durable active-session recovery, and global scheduling. Completed dashboard histories and saved workflows survive restart; active sessions, pending questions, and unapproved drafts do not. The manual demo balance editor uses per-tab session storage; its values are not shared with separate automation contexts. Future work should extend verified resume states and artifact compatibility before adding infrastructure. No public deployment or submission is part of the implementation itself.
