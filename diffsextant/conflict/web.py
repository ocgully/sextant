"""HTTP-shape-agnostic handlers for the web view (phase 1D).

This module mirrors the ``sextant.web.server`` style: pure functions
that take a parsed body / path and return a JSON-shaped dict, so the
1C server can dispatch to them without coupling. An ``attach_conflict``
helper monkey-patches a stdlib ``BaseHTTPRequestHandler`` for cases
where the conflict view runs standalone.

Routes:
    GET  /api/conflict/<path>           -> handle_conflict_get
    POST /api/conflict/<path>/resolve   -> handle_conflict_resolve
"""
from __future__ import annotations

import json
import urllib.parse
from http import HTTPStatus
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from diffsextant.conflict.analyze import analyze_file
from diffsextant.conflict.types import ConflictFile


# ---------------------------------------------------------------------------
# pure handlers
# ---------------------------------------------------------------------------


def handle_conflict_get(path_arg: str, *, cwd: Optional[Path] = None) -> Dict[str, Any]:
    """Return the parsed + classified picture for a conflicted file."""
    cwd = (cwd or Path.cwd()).resolve()
    file_path = _resolve_target(cwd, path_arg)
    if file_path is None:
        return {"error": f"path escapes the project root: {path_arg!r}"}
    if not file_path.exists():
        return {"error": f"no such file: {path_arg}"}
    try:
        cf = analyze_file(file_path, cwd=cwd)
    except Exception as e:
        return {"error": f"analyze failed: {e}"}
    return cf.to_dict()


def handle_conflict_resolve(
    path_arg: str, body: Dict[str, Any], *, cwd: Optional[Path] = None
) -> Dict[str, Any]:
    """Apply a chosen suggestion to a region; rewrite the file."""
    cwd = (cwd or Path.cwd()).resolve()
    file_path = _resolve_target(cwd, path_arg)
    if file_path is None:
        return {"error": f"path escapes the project root: {path_arg!r}"}
    if not file_path.exists():
        return {"error": f"no such file: {path_arg}"}
    if not isinstance(body, dict):
        return {"error": "body must be a JSON object"}
    region_index = body.get("region_index")
    suggestion_key = body.get("suggestion_key")
    if not isinstance(region_index, int) or not isinstance(suggestion_key, str):
        return {"error": "expected {region_index:int, suggestion_key:str}"}

    cf = analyze_file(file_path, cwd=cwd)
    region = next((r for r in cf.regions if r.index == region_index), None)
    if region is None:
        return {"error": f"no region with index {region_index}"}
    sug = next((s for s in region.suggestions if s.key == suggestion_key), None)
    if sug is None:
        return {"error": f"no suggestion `{suggestion_key}` on region #{region_index}"}
    if not sug.auto_apply or sug.body is None:
        return {
            "error": f"suggestion `{suggestion_key}` is not auto-applicable",
            "manual_required": True,
        }

    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=False)
    new_body_lines = sug.body.splitlines() if sug.body else []
    lines[region.line_start - 1: region.line_end] = new_body_lines
    out = "\n".join(lines)
    if text.endswith("\n"):
        out += "\n"
    file_path.write_text(out, encoding="utf-8")

    cf2 = analyze_file(file_path, cwd=cwd)
    return {
        "applied": True,
        "region_index": region_index,
        "suggestion_key": suggestion_key,
        "remaining_regions": len(cf2.regions),
        "picture": cf2.to_dict(),
    }


def _resolve_target(cwd: Path, path_arg: str) -> Optional[Path]:
    """Resolve a request-path-shaped argument into a real Path under
    `cwd`. Returns None if it escapes the root (defence in depth — the
    server should already gate this, but the handler is the second line)."""
    decoded = urllib.parse.unquote(path_arg)
    candidate = (cwd / decoded).resolve()
    try:
        candidate.relative_to(cwd)
    except ValueError:
        return None
    return candidate


# ---------------------------------------------------------------------------
# stdlib http.server attach helper (so 1D works standalone)
# ---------------------------------------------------------------------------


def attach_conflict(handler_class, *, cwd: Optional[Path] = None):
    """Monkey-patch a BaseHTTPRequestHandler subclass so it answers
    GET /api/conflict/<path>            and
    POST /api/conflict/<path>/resolve

    Anything else falls through to the existing do_GET / do_POST so 1C
    routes keep working.
    """
    cwd = cwd or Path.cwd()
    existing_get = getattr(handler_class, "do_GET", None)
    existing_post = getattr(handler_class, "do_POST", None)

    def _api_path(p: str) -> Optional[Tuple[str, bool]]:
        prefix = "/api/conflict/"
        if not p.startswith(prefix):
            return None
        rest = p[len(prefix):]
        if rest.endswith("/resolve"):
            return rest[: -len("/resolve")], True
        return rest, False

    def do_GET(self):  # noqa: N802
        m = _api_path(self.path)
        if m is None:
            if existing_get is not None:
                return existing_get(self)
            self.send_error(HTTPStatus.NOT_FOUND, "no route")
            return
        path_arg, is_resolve = m
        if is_resolve:
            self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "POST only")
            return
        payload = handle_conflict_get(path_arg, cwd=cwd)
        status = HTTPStatus.OK if "error" not in payload else HTTPStatus.BAD_REQUEST
        _send_json(self, status, payload)

    def do_POST(self):  # noqa: N802
        m = _api_path(self.path)
        if m is None or not m[1]:
            if existing_post is not None:
                return existing_post(self)
            self.send_error(HTTPStatus.NOT_FOUND, "no route")
            return
        path_arg, _ = m
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            _send_json(self, HTTPStatus.BAD_REQUEST,
                       {"error": f"invalid JSON: {e}"})
            return
        payload = handle_conflict_resolve(path_arg, body, cwd=cwd)
        status = HTTPStatus.OK if "error" not in payload else HTTPStatus.BAD_REQUEST
        _send_json(self, status, payload)

    handler_class.do_GET = do_GET
    handler_class.do_POST = do_POST
    return handler_class


def _send_json(handler, status: HTTPStatus, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
