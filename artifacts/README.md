# Workflow examples

| File | Inputs and behavior | Provenance |
| --- | --- | --- |
| `savings_balance.json` | Member ID; read and verify the savings balance. | Hand-authored fixture |
| `update_savings_balance.json` | Member ID and new balance; update the synthetic demo without confirmation and verify the read-back. | Hand-authored schema 1.2 fixture |

Use the [evidence guide](../evidence/README.md) for model-discovered artifacts and their source logs. Keep that evidence in the assignment submission. You can replay these hand-authored examples without it or an API key.

Find dashboard-created workflows in ignored `runs/dashboard/`. To share one, inspect its `capability.json` for sensitive data, then copy it here with a descriptive filename. Schema 2.0 artifacts include a target URL and page metadata and require dashboard replay. Keep external targets reachable; for bundled-demo workflows, the dashboard can supply its current demo instance.
