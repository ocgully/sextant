"""Smoke tests for `diffsextant web` (phase 1C).

Spins up the stdlib http.server in a thread against a tmp git repo and
hits each endpoint. Verifies:
  - / serves the SPA HTML
  - /static/app.js + view modules + style.css serve
  - /api/meta returns project root + version
  - /api/diff/current classifies HEAD~1..HEAD into operations
  - /api/diff?ref1=&ref2= explicit-range works
  - /api/explain?commit= works
  - /api/timeline?range= returns per-commit summaries
  - 404 on bad routes
  - 400 on missing required query params
"""
from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from diffsextant.web import server as web_server
from tests.conftest import init_repo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _sh(args, cwd: Path) -> str:
    r = subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)
    return r.stdout


def _build_two_commit_repo(tmp_path: Path) -> Path:
    """Two commits with a real Python rename so the classifier has work
    to do — guarantees /api/diff/current returns at least one op."""
    repo = init_repo(tmp_path)
    (repo / "mod.py").write_text(
        "def compute_total(items):\n"
        "    s = 0\n"
        "    for it in items:\n"
        "        s += it\n"
        "    return s\n",
        encoding="utf-8",
    )
    _sh(["git", "add", "-A"], repo)
    _sh(["git", "commit", "-q", "-m", "first"], repo)
    (repo / "mod.py").write_text(
        "def compute_sum(items):\n"
        "    total = 0\n"
        "    for it in items:\n"
        "        total += it\n"
        "    return total\n",
        encoding="utf-8",
    )
    _sh(["git", "add", "-A"], repo)
    _sh(["git", "commit", "-q", "-m", "rename compute_total -> compute_sum"], repo)
    return repo


def _serve(repo: Path, port: int) -> Tuple[Any, threading.Thread]:
    server = web_server._ThreadingHTTPServer(("127.0.0.1", port), web_server.DiffSextantWebHandler)
    server.project_root = repo  # type: ignore[attr-defined]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.05):
                break
        except OSError:
            time.sleep(0.02)
    return server, t


def _get(port: int, path: str) -> Tuple[int, bytes, str]:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body = e.read() if hasattr(e, "read") else b""
        return e.code, body, e.headers.get("Content-Type", "") if e.headers else ""


def _get_json(port: int, path: str) -> Tuple[int, Dict[str, Any], str]:
    code, body, ctype = _get(port, path)
    try:
        return code, json.loads(body.decode("utf-8")), ctype
    except Exception:
        return code, {"_raw": body.decode("utf-8", errors="replace")}, ctype


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def served_repo(tmp_path: Path):
    repo = _build_two_commit_repo(tmp_path)
    port = _free_port()
    server, _t = _serve(repo, port)
    try:
        yield (repo, port)
    finally:
        server.shutdown()
        server.server_close()


def test_index_serves_html(served_repo):
    _, port = served_repo
    code, body, ctype = _get(port, "/")
    assert code == 200
    assert "text/html" in ctype
    text = body.decode("utf-8")
    assert "<title>DiffSextant</title>" in text
    assert 'data-mode="ops"' in text
    assert 'data-mode="classic"' in text
    assert 'data-mode="timeline"' in text


def test_static_assets_serve(served_repo):
    _, port = served_repo
    for asset, ctype_frag in [
        ("/static/app.js", "javascript"),
        ("/static/style.css", "css"),
        ("/static/view_operations.js", "javascript"),
        ("/static/view_classic.js", "javascript"),
        ("/static/view_timeline.js", "javascript"),
    ]:
        code, body, ctype = _get(port, asset)
        assert code == 200, f"{asset} -> {code}"
        assert ctype_frag in ctype
        assert len(body) > 100, f"{asset} body suspiciously short ({len(body)} bytes)"


def test_meta_endpoint(served_repo):
    repo, port = served_repo
    code, payload, _ = _get_json(port, "/api/meta")
    assert code == 200
    assert payload["project_root"]
    assert payload["diffsextant_version"]
    # legacy alias kept one cycle
    assert payload["sextant_version"] == payload["diffsextant_version"]
    assert payload["head"]


def test_diff_current_returns_operations(served_repo):
    _, port = served_repo
    code, payload, _ = _get_json(port, "/api/diff/current")
    assert code == 200
    assert "operations" in payload
    assert "files" in payload
    assert isinstance(payload["operations"], list)
    assert len(payload["operations"]) >= 1
    op = payload["operations"][0]
    assert "kind" in op
    assert "summary" in op
    assert "file" in op


def test_diff_explicit_range(served_repo):
    _, port = served_repo
    code, payload, _ = _get_json(port, "/api/diff?ref1=HEAD~1&ref2=HEAD")
    assert code == 200
    assert "operations" in payload


def test_diff_missing_refs_returns_400(served_repo):
    _, port = served_repo
    code, payload, _ = _get_json(port, "/api/diff?ref1=HEAD~1")
    assert code == 400
    assert "error" in payload


def test_explain_endpoint(served_repo):
    _, port = served_repo
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(served_repo[0]), capture_output=True, text=True, check=True,
    ).stdout.strip()
    code, payload, _ = _get_json(port, f"/api/explain?commit={head}")
    assert code == 200
    assert "operations" in payload


def test_explain_missing_commit_returns_400(served_repo):
    _, port = served_repo
    code, payload, _ = _get_json(port, "/api/explain")
    assert code == 400


def test_timeline_endpoint(served_repo):
    _, port = served_repo
    code, payload, _ = _get_json(port, "/api/timeline?range=HEAD~1..HEAD")
    assert code == 200
    assert "commits" in payload
    assert isinstance(payload["commits"], list)
    assert len(payload["commits"]) == 1
    c = payload["commits"][0]
    assert "sha" in c
    assert "subject" in c
    assert "kind_counts" in c
    assert "op_count" in c


def test_timeline_missing_range_returns_400(served_repo):
    _, port = served_repo
    code, payload, _ = _get_json(port, "/api/timeline")
    assert code == 400


def test_timeline_bad_range(served_repo):
    _, port = served_repo
    code, payload, _ = _get_json(port, "/api/timeline?range=not-a-range")
    assert code == 200          # the handler returns a structured error
    assert "error" in payload   # not an HTTP error — the JSON carries it


def test_unknown_route_404(served_repo):
    _, port = served_repo
    code, payload, _ = _get_json(port, "/api/does-not-exist")
    assert code == 404
    assert "error" in payload


def test_static_path_traversal_blocked(served_repo):
    _, port = served_repo
    code, _, _ = _get(port, "/static/../server.py")
    assert code == 404
