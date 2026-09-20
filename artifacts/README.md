# Capability fixture

`savings_balance.json` is a hand-authored replay fixture, not a discovery recording. It contains parameter references, not customer values. Genuine discovery artifacts and their provenance are indexed in [the evidence guide](../evidence/README.md).

Dashboard-created workflows are stored in ignored `runs/dashboard/`. To share one, review its contents and copy only its `capability.json` to this directory with a descriptive filename.

Workflow artifacts are executable inputs; evidence logs are optional records supporting claims about their creation and behavior. This fixture works without the `evidence/` folder or an API key. For a compact public demonstration, see the six-file [included evidence set](../evidence/README.md#included-demonstration-set).
