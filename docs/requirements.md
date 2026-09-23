# Requirements coverage

Evaluate the reference implementation through the synthetic-bank CLI (schema 1.x). The table separates that coverage from the experimental dashboard creation path (schema 2.0).

| Assignment requirement | Reference path and evidence | Generic extension limitation |
| --- | --- | --- |
| 3.1 Goal-driven live loop | Natural-language goal plus synthetic target; genuine Gemini discovery in `evidence/`. | Real Gemini 3.5 assisted NGPF run retained; narrow site/control support. |
| 3.2 Structured capability | Strict versioned steps, parameter references, input/output contracts, roles/names, checkpoint, supported recovery rules. | Page-derived inputs; outputs remain generic text. Assisted runs produce no artifact. |
| 3.3 Deterministic replay | No model calls; output/member/checkpoint checks; not-found business outcome, permission failure, bounded recovery. Current acceptance records cover these. | Control/template checks exist; general business outcomes and replay recovery are incomplete. |
| 3.4 Safety | Configurable demo host/path/action allowlist; sanitized vocabulary and masked screenshots. Synthetic data only. | Mostly hardcoded restrictions; page metadata can contain sensitive data. Not suitable for regulated data. |
| 3.5 Observability | Structured decisions/actions/outcomes, handoff context, masked permission-failure screenshot. | Structured events but no richer redacted failure snapshot. |
| 3.6 Human handoff | Same live browser, explicit ownership, captured recognized actions, resume verification. Historical manual evidence and current scripted-operator regression. | Discovery handoff exists; replay takeover and reusable manual repair capture do not. |
| 3.7 Heterogeneity/scale design | REPORT describes proposed surface adapters, shared vendor capabilities, tenant overrides, compatibility checks and isolation. | Desktop, tenant plumbing, and cross-tenant replay are not implemented or claimed. |
| Deliverables | README includes exact live discovery/replay and manual-handoff commands; REPORT uses all seven required headings; evidence is retained. | Extension is labeled separately rather than presented as acceptance coverage. |

The reference adapter supplies a banking action catalog and interprets known states. Review the evidence provenance before drawing conclusions from a test: original provider runs, scripted model responses, and scripted operators validate different parts of the system. See REPORT for cuts and proposed extensions. Before submitting, check public repository visibility and the rendered report length.
