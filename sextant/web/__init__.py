"""Sextant web UI (phase 1C + phase 1E `/api/discuss` + phase 1D `/api/conflict`).

Stdlib `http.server` + Preact (esm.sh, no build). Mirrors the stack used by
Hopewell and Pedia so the three tools share one mental model. Read-only:
all writes go through the CLI.

Phase 1C ships the operations / classic-text / timeline views.
Phase 1D adds `/api/conflict/<file>` for conflict resolution UX.
Phase 1E adds `/api/discuss` + `sextant_discuss.js` toolbar button.

Public entry: `sextant.web.server.run(project_root, port=9881, open_browser=False)`.
The `sextant web` CLI subcommand wires through to `run(...)`.
"""
