"""Stdlib http.server for `sextant web` (phase 1C of HW-0056).

Design notes (mirrors Pedia's web/server.py — same stdlib-only pattern):

* Stdlib only. `http.server` + `subprocess` + `json` + `pathlib`. No
  FastAPI, no bundler, no SSE. Sextant is commit-paced — when the diff
  changes you click Refresh (or the URL hash refreshes a re-fetch).
* Read-only. Every handler is GET; mutations live in the CLI (and 1D's
  conflict resolver, when that lands).
* Thin adapter. Every endpoint calls into the same library entrypoints
  the CLI uses (`sextant.tree_delta.classify_diff`, `sextant.git_context`,
  `sextant.risk`). No alternate code path.
* The renderer/operation taxonomy is owned by phase 1A; this server
  just shapes the JSON for the browser.

CLI entry: `sextant web --port N [--open]` -> `run(project_root, ...)`.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from sextant import __version__ as SEXTANT_VERSION


STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Diff handlers — thin wrappers over the classifier pipeline
# ---------------------------------------------------------------------------


def _run_git(args: List[str], cwd: Path) -> Optional[str]:
    """Run a git command, return stdout or None on failure (mirrors
    tree_delta._run_git but kept private here so the web layer never
    reaches into a private name)."""
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def _classify(root: Path, ref1: str, ref2: str, *,
              risk_mode: str = "basic") -> Dict[str, Any]:
    """Run the classifier and return the to_dict() shape used by the CLI's
    --format json output. Phase 1B's git_driver and 1C's web layer
    share this exact payload."""
    from sextant.git_context import collect as collect_ctx
    from sextant.tree_delta import classify_diff
    from sextant.risk import enrich

    ctx = collect_ctx(root, ref1=ref1, ref2=ref2)
    if not ctx.is_repo:
        return {"error": f"not a git worktree: {root}"}
    result = classify_diff(ref1, ref2, cwd=root, git_ctx=ctx)
    enrich(result, cwd=root, mode=risk_mode)
    return result.to_dict()


def handle_diff(root: Path, ref1: str, ref2: str, risk: str = "basic") -> Dict[str, Any]:
    return _classify(root, ref1, ref2, risk_mode=risk)


def handle_diff_current(root: Path, risk: str = "basic") -> Dict[str, Any]:
    """Default: HEAD~1..HEAD. Falls back to an explanatory error if HEAD~1
    doesn't exist (single-commit repos)."""
    if _run_git(["rev-parse", "HEAD~1"], root) is None:
        return {
            "error": "no HEAD~1 — single-commit repo. Pass ?ref1=&ref2= explicitly.",
            "operations": [], "files": [], "git_context": None, "warnings": [],
        }
    return _classify(root, "HEAD~1", "HEAD", risk_mode=risk)


def handle_explain(root: Path, commit: str, risk: str = "basic") -> Dict[str, Any]:
    return _classify(root, f"{commit}^", commit, risk_mode=risk)


def handle_timeline(root: Path, range_spec: str, risk: str = "basic",
                    max_commits: int = 50) -> Dict[str, Any]:
    """Walk a `<a>..<b>` range, classify each commit individually, return a
    list of per-commit summaries.

    For phase 1C we deliberately keep this O(N commits * classifier_cost):
    operation streams across a PR are usually small enough. A future
    optimization would be parallelization or a cumulative diff per chunk.
    """
    parts = range_spec.split("..", 1)
    if len(parts) != 2 or not all(parts):
        return {"error": f"bad range: {range_spec!r} (expected '<a>..<b>')",
                "commits": []}
    lo, hi = parts
    out = _run_git(
        ["log", "--reverse", "--pretty=format:%H%x09%s%x09%an%x09%ae%x09%cI",
         f"{lo}..{hi}"],
        root,
    )
    if out is None:
        return {"error": f"git log {lo}..{hi} failed", "commits": []}
    commits: List[Dict[str, Any]] = []
    lines = [l for l in out.splitlines() if l.strip()]
    if len(lines) > max_commits:
        # Tail the most-recent N to keep the timeline tractable on large PRs
        lines = lines[-max_commits:]
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        sha, subject, an, ae, ts = parts[:5]
        # classify <sha>^..<sha>
        try:
            entry = _classify(root, f"{sha}^", sha, risk_mode=risk)
            ops = entry.get("operations", []) or []
            kinds: Dict[str, int] = {}
            for op in ops:
                kinds[op.get("kind", "?")] = kinds.get(op.get("kind", "?"), 0) + 1
            files_touched = sorted({
                f["path_after"] or f["path_before"] or "?"
                for f in entry.get("files", []) or []
            })
            risks = [op.get("risk") for op in ops if op.get("risk")]
            top_risk = max((r.get("score", 0.0) for r in risks if r), default=0.0)
            commits.append({
                "sha": sha,
                "short_sha": sha[:8],
                "subject": subject,
                "author_name": an,
                "author_email": ae,
                "timestamp": ts,
                "op_count": len(ops),
                "kind_counts": kinds,
                "files_touched": files_touched,
                "max_risk_score": top_risk,
                "warnings": entry.get("warnings") or [],
            })
        except Exception as e:  # pragma: no cover — best-effort timeline
            commits.append({
                "sha": sha,
                "short_sha": sha[:8],
                "subject": subject,
                "error": f"{type(e).__name__}: {e}",
            })
    return {"range": range_spec, "lo": lo, "hi": hi, "commits": commits}


def handle_meta(root: Path) -> Dict[str, Any]:
    head = (_run_git(["rev-parse", "HEAD"], root) or "").strip() or None
    branch = (_run_git(["rev-parse", "--abbrev-ref", "HEAD"], root) or "").strip() or None
    return {
        "project_root": str(root),
        "sextant_version": SEXTANT_VERSION,
        "head": head,
        "branch": branch,
    }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------


class SextantWebHandler(http.server.BaseHTTPRequestHandler):
    server_version = f"sextant-web/{SEXTANT_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
        sys.stderr.write(
            "[sextant-web] %s - %s\n" % (self.address_string(), fmt % args)
        )

    # -- helpers -----------------------------------------------------------

    def _send_json(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, code: int, message: str) -> None:
        self._send_json(code, {"error": message})

    def _send_static(self, rel: str) -> None:
        rel = rel.lstrip("/").replace("..", "")
        target = STATIC_DIR / rel
        if not target.is_file():
            self._send_error_json(404, f"not found: {rel}")
            return
        ctype = _guess_mime(target.name)
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- routing -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        root: Path = self.server.project_root  # type: ignore[attr-defined]

        try:
            if path == "/" or path == "/index.html":
                return self._send_static("index.html")
            if path.startswith("/static/"):
                return self._send_static(path[len("/static/"):])

            if path == "/api/meta":
                return self._send_json(200, handle_meta(root))

            if path == "/api/diff":
                ref1 = (qs.get("ref1") or [""])[0]
                ref2 = (qs.get("ref2") or [""])[0]
                if not ref1 or not ref2:
                    return self._send_error_json(400, "missing ?ref1= or ?ref2=")
                risk = (qs.get("risk") or ["basic"])[0]
                return self._send_json(200, handle_diff(root, ref1, ref2, risk=risk))

            if path == "/api/diff/current":
                risk = (qs.get("risk") or ["basic"])[0]
                return self._send_json(200, handle_diff_current(root, risk=risk))

            if path == "/api/explain":
                commit = (qs.get("commit") or [""])[0]
                if not commit:
                    return self._send_error_json(400, "missing ?commit=")
                risk = (qs.get("risk") or ["basic"])[0]
                return self._send_json(200, handle_explain(root, commit, risk=risk))

            if path == "/api/timeline":
                rng = (qs.get("range") or [""])[0]
                if not rng:
                    return self._send_error_json(400, "missing ?range=<a>..<b>")
                risk = (qs.get("risk") or ["basic"])[0]
                return self._send_json(200, handle_timeline(root, rng, risk=risk))

            return self._send_error_json(404, f"no route: {path}")
        except BrokenPipeError:
            return
        except Exception as e:  # pragma: no cover — best-effort error render
            try:
                self._send_error_json(500, f"{type(e).__name__}: {e}")
            except Exception:
                pass


def _guess_mime(name: str) -> str:
    n = name.lower()
    if n.endswith(".html"):
        return "text/html; charset=utf-8"
    if n.endswith(".js") or n.endswith(".mjs"):
        return "application/javascript; charset=utf-8"
    if n.endswith(".css"):
        return "text/css; charset=utf-8"
    if n.endswith(".json"):
        return "application/json; charset=utf-8"
    if n.endswith(".svg"):
        return "image/svg+xml"
    return "application/octet-stream"


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """One thread per request. Classifier calls are CPU-bound but short;
    threading lets a slow client (or a held-open SSE-less browser) avoid
    blocking the next request."""

    daemon_threads = True
    allow_reuse_address = True


def run(
    project_root: Path,
    *,
    port: int = 9881,
    open_browser: bool = False,
    host: str = "127.0.0.1",
) -> int:
    """Start the read-only Sextant web UI. Blocks until Ctrl+C."""
    if not project_root.is_dir():
        sys.stderr.write(f"error: not a directory: {project_root}\n")
        return 2
    if not (project_root / ".git").exists():
        # not necessarily fatal — sextant may be reading a worktree —
        # but warn so the user knows /api/diff/current will likely 4xx.
        sys.stderr.write(
            f"warning: no .git/ at {project_root} — diff endpoints will return errors\n"
        )

    server = _ThreadingHTTPServer((host, port), SextantWebHandler)
    server.project_root = project_root  # type: ignore[attr-defined]
    url = f"http://{host}:{port}/"
    sys.stdout.write(
        f"sextant web {SEXTANT_VERSION} -- serving {project_root} at {url}\n"
        "(read-only; Ctrl+C to stop)\n"
    )
    if open_browser:
        def _open() -> None:
            time.sleep(0.4)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=_open, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stdout.write("\nsextant web: stopping\n")
    finally:
        server.server_close()
    return 0
