"""Sextant web UI (phase 1C).

Stdlib http.server + Preact (esm.sh, no build). Mirrors the stack used by
Hopewell and Pedia so the three tools share one mental model. Read-only:
all writes go through the CLI.

Public entry: `sextant.web.server.run(project_root, port=9881, open_browser=False)`.
The `sextant web` CLI subcommand wires through to `run(...)`.
"""
