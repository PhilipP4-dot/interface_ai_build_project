# Installation verification

Verified September 18, 2026 on Windows with Python 3.12.

- Created a separate virtual environment at `tmp/install-check-20260918`, without access to the existing environment's installed packages.
- Installed all pinned dependencies from `requirements.lock`. Package downloads used the machine's pip cache where available; this was not an empty-cache machine test.
- Installed the project using the README's editable-install flags. `pip check` reported no broken requirements.
- Ran the documented Chromium installer successfully. The machine already had Playwright browser files, so this does not prove a first-time browser download on another machine.
- Replayed the September 18 discovered capability for synthetic member 67890. The result was `completed` with balance `842.10`; no model calls were made. The installation log is retained locally, outside the published demonstration set.
- Built a normal wheel and inspected its 18 entries. It includes `interface_automation/demo.html` and excludes environment files and run/evidence directories. The wheel build is a packaging check; the documented installation and replay used editable mode.

No API credentials were copied into the isolated environment. Existing live-provider evidence was reused as an input artifact. The environment and wheel are ignored temporary outputs, not submission artifacts. No publication occurred.

The supported installation remains a source checkout on Windows/Python 3.12. Live discovery resolves its credential file and budget ledger relative to that source checkout; the wheel is not advertised as a standalone installed-service deployment.

Packaging rechecked September 20, 2026 with an offline wheel build from the current checkout. Both dashboard.html and demo.html are included; environment files, runtime output, and evidence directories are excluded. The installed environment passes pip check. This does not replace the separate-environment installation check above or claim a fresh download test.
