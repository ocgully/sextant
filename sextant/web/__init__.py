"""Sextant web UI (phase 1C scaffold + phase 1E `/api/discuss`).

Stdlib `http.server` + Preact (esm.sh, no build). Mirrors the stack
used by Hopewell and Pedia so the three tools share one mental model.

Phase 1E adds:
  - `/api/discuss` endpoint  → wraps `sextant.llm.discuss.discuss`
  - `sextant_discuss.js`     → toolbar button (mountDiscussButton)

The full server lands with phase 1C; `sextant.web.server.attach_discuss`
is exposed for the 1C author to register the discuss endpoint into
whatever request-routing they pick.
"""
