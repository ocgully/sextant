"""Sextant web server — phase 1E lays down the `/api/discuss` endpoint.

Phase 1C owns the rest of the server (operations / classic-text /
timeline views). To avoid stomping mid-flight 1C work, this module
exposes:

    handle_discuss(request_body, *, cwd) -> dict
        Pure function: takes a JSON body (`{ref1, ref2, agent?, files?}`),
        returns the JSON payload `/api/discuss` should respond with.
        Coalesces around `sextant.llm.discuss.discuss`. No HTTP coupling.

    attach_discuss(request_handler_class, *, cwd)
        Optional helper: monkey-patches a stdlib `BaseHTTPRequestHandler`
        subclass so that POST `/api/discuss` is routed to
        `handle_discuss`. The 1C author can call this from their own
        `run(...)` after building the rest of the route table, or
        re-implement equivalent dispatch — either is fine.

The handler logic is HTTP-shape-agnostic so the 1C server can plug it
in without diff conflicts; the test suite drives `handle_discuss`
directly.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, Optional


def handle_discuss(body: Dict[str, Any], *, cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Build a discuss bundle for the request body and return the JSON
    payload. Never raises — errors come back as `{"error": "..."}`.
    """
    cwd = (cwd or Path.cwd()).resolve()
    if not isinstance(body, dict):
        return {"error": "body must be a JSON object"}
    ref1 = body.get("ref1")
    ref2 = body.get("ref2")
    if not ref1 or not ref2:
        return {"error": "ref1 and ref2 are required"}
    agent = body.get("agent")
    files = body.get("files") or None

    try:
        from sextant.llm.discuss import discuss as _discuss
        result = _discuss(ref1, ref2, cwd=cwd, agent=agent, files=files)
    except Exception as e:
        return {"error": f"discuss failed: {e}"}
    return result


def attach_discuss(handler_class, *, cwd: Optional[Path] = None):
    """Monkey-patch a BaseHTTPRequestHandler subclass so it answers
    POST `/api/discuss`. Delegates everything else to the existing
    `do_POST` (if any). The 1C author may use this or wire `/api/discuss`
    themselves — both call the same `handle_discuss` underneath.
    """
    cwd = cwd or Path.cwd()
    existing_post = getattr(handler_class, "do_POST", None)

    def do_POST(self):  # noqa: N802 — stdlib naming
        if self.path != "/api/discuss":
            if existing_post is not None:
                return existing_post(self)
            self.send_error(HTTPStatus.NOT_FOUND, "no route")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON: {e}"})
            return
        payload = handle_discuss(body, cwd=cwd)
        status = HTTPStatus.OK if "error" not in payload else HTTPStatus.BAD_REQUEST
        self._send_json(status, payload)

    def _send_json(self, status: HTTPStatus, payload: Dict[str, Any]):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    handler_class.do_POST = do_POST
    handler_class._send_json = _send_json  # type: ignore[attr-defined]
    return handler_class
