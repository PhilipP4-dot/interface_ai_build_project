# Installation verification

Supported setup: a Windows source checkout with Python 3.12. These checks used the machine's package cache and existing Playwright browser files. A fresh download on another machine remains untested.

| Check | September 18, 2026 result |
| --- | --- |
| Separate environment | Installed pinned dependencies in `tmp/install-check-20260918`, without access to the working environment's packages. |
| Editable install | Used the README flags; `pip check` found no broken requirements. |
| Chromium setup | Ran the documented installer against existing browser files. |
| Provider-free replay | Replayed the September 18 discovered artifact for synthetic member 67890; returned `completed` and balance `842.10`. |
| Wheel inspection | Inspected 18 entries; found `demo.html` and no environment files or run/evidence directories. |

The isolated environment used no API credentials. Find its original installation log in local temporary storage; the submission retains the discovered artifact as the reproducible input. Keep the temporary environment and wheel outside Git.

On September 20, an offline wheel build included both `dashboard.html` and `demo.html`, excluded environment files and runtime/evidence directories, and the installed environment passed `pip check`. This was a packaging check; the documented execution used a source checkout. Live discovery resolves credentials and the budget ledger relative to that checkout.

For checks against the current code, run the [acceptance script](../scripts/verify_submission.py) and tests listed in the [README](../README.md#verification-and-design).
