"""sextant CLI — argparse dispatcher.

Phase 1A commands:
  sextant diff <ref1> <ref2> [files...]
  sextant explain <commit>
  sextant check <path>
  sextant cache {clear|stats}
  sextant config {get|set|list}

Phase 1B commands:
  sextant register-git-driver [--scope user|repo] [--uninstall]
  sextant diff --git-driver-mode <path> <old-file> <old-hex> <old-mode>
                                 <new-file> <new-hex> <new-mode>
    (internal — invoked by git when sextant is registered as a diff driver)

Phase 1C commands:
  sextant web [--port N] [--open] [--host H]
    Launches the local Preact + esm.sh web UI (operations / classic-text /
    timeline views). Stdlib http.server on a single port; no auth, no SSE.
    See sextant/web/server.py for the full route table.

Deferred (phases 1D-1E):
  sextant conflict / export-to-hopewell / discuss / etc.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

from sextant import __version__


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def cmd_diff(args) -> int:
    from sextant.git_context import collect as collect_ctx
    from sextant.tree_delta import classify_diff
    from sextant.risk import enrich
    from sextant.render import render_json, render_text

    # Phase 1B: when invoked by git as an external diff driver, ref1/ref2
    # carry the first two of git's 7 positional args, and `args.files`
    # carries the remaining 5. Reshape and dispatch through git_driver.
    if args.git_driver_mode:
        from sextant.git_driver import GitDriverInvocation, render_driver_invocation
        positional = [args.ref1, args.ref2, *(args.files or [])]
        try:
            inv = GitDriverInvocation.from_argv(positional)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        return render_driver_invocation(inv, fmt=args.format)

    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    ctx = collect_ctx(cwd, ref1=args.ref1, ref2=args.ref2)
    if not ctx.is_repo:
        print(f"error: {cwd} is not a git worktree", file=sys.stderr)
        return 2

    result = classify_diff(args.ref1, args.ref2, cwd=cwd, files=args.files or None,
                           git_ctx=ctx)

    # Optional filter by kinds
    if args.patterns:
        wanted = set(k.strip() for k in args.patterns.split(","))
        result.operations = [op for op in result.operations if op.kind.value in wanted]

    # Risk enrichment
    enrich(result, cwd=cwd, mode=args.risk)

    if args.format == "json":
        sys.stdout.write(render_json(result) + "\n")
    else:
        sys.stdout.write(render_text(result, threshold=0.0, show_evidence=args.show_evidence))

    return 0


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------


def cmd_explain(args) -> int:
    """Same as `sextant diff <commit>^ <commit>`."""
    from sextant.git_context import collect as collect_ctx
    from sextant.tree_delta import classify_diff
    from sextant.risk import enrich
    from sextant.render import render_json, render_text

    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    ref1 = f"{args.commit}^"
    ref2 = args.commit
    ctx = collect_ctx(cwd, ref1=ref1, ref2=ref2)
    if not ctx.is_repo:
        print(f"error: {cwd} is not a git worktree", file=sys.stderr)
        return 2
    result = classify_diff(ref1, ref2, cwd=cwd, git_ctx=ctx)
    enrich(result, cwd=cwd, mode=args.risk)
    if args.format == "json":
        sys.stdout.write(render_json(result) + "\n")
    else:
        sys.stdout.write(render_text(result, show_evidence=args.show_evidence))
    return 0


# ---------------------------------------------------------------------------
# check — standalone malformed detection
# ---------------------------------------------------------------------------


def cmd_check(args) -> int:
    from sextant.ops.malformed import detect
    from sextant.parse import detect_language, parse_source

    path = Path(args.path)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 2

    lang = detect_language(str(path))
    sig = detect(text, language=lang)
    parse = parse_source(text, lang) if lang else None

    payload = {
        "path": str(path),
        "language": lang,
        "malformed": sig is not None,
        "signals": sig["signals"] if sig else [],
        "details": sig["details"] if sig else {},
        "parse_ok": bool(parse and parse.parseable and parse.error_count == 0) if parse else None,
        "parse_error_count": parse.error_count if parse else None,
    }

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        if sig is None:
            sys.stdout.write(f"OK: {path} — no malformed signals\n")
            if parse and parse.tree is not None:
                sys.stdout.write(f"    language: {lang}  errors: {parse.error_count}\n")
        else:
            sys.stdout.write(f"MALFORMED: {path}\n")
            for s in sig["signals"]:
                sys.stdout.write(f"  - {s}\n")
            if sig["details"]:
                sys.stdout.write(f"  details: {sig['details']}\n")
    return 1 if sig else 0


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


def cmd_cache(args) -> int:
    from sextant import cache as cache_mod
    cwd = Path.cwd()
    if args.action == "stats":
        s = cache_mod.stats(cwd)
        sys.stdout.write(json.dumps(s, indent=2) + "\n")
        return 0
    if args.action == "clear":
        ok = cache_mod.clear(cwd)
        if ok:
            sys.stdout.write(f"cleared {cwd / '.sextant' / 'cache'}\n")
        else:
            sys.stdout.write("no cache to clear\n")
        return 0
    return 2


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def cmd_config(args) -> int:
    from sextant import config as cfg_mod
    if args.action == "list":
        sys.stdout.write(json.dumps(cfg_mod.load(), indent=2, sort_keys=True) + "\n")
        return 0
    if args.action == "get":
        if not args.key:
            print("error: `config get` requires a key", file=sys.stderr)
            return 2
        v = cfg_mod.get_key(args.key)
        sys.stdout.write(json.dumps(v) + "\n")
        return 0
    if args.action == "set":
        if not args.key or args.value is None:
            print("error: `config set` requires key + value", file=sys.stderr)
            return 2
        path = cfg_mod.set_key(args.key, args.value)
        sys.stdout.write(f"wrote {path}\n")
        return 0
    return 2


# ---------------------------------------------------------------------------
# register-git-driver  (phase 1B — see sextant/git_driver.py)
# ---------------------------------------------------------------------------


def cmd_register_git_driver(args) -> int:
    from sextant.git_driver import install, uninstall
    if args.uninstall:
        return uninstall(scope=args.scope)
    return install(scope=args.scope)


# ---------------------------------------------------------------------------
# web (phase 1C) — see sextant/web/server.py for route table
# ---------------------------------------------------------------------------


def cmd_web(args) -> int:
    from sextant.web.server import run as run_web
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    return run_web(
        cwd,
        port=args.port,
        host=args.host,
        open_browser=args.open,
    )


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sextant",
        description="Semantic-operation diff classifier (phase 1A).",
    )
    p.add_argument("--version", action="version", version=f"sextant {__version__}")

    sub = p.add_subparsers(dest="cmd", required=True)

    # diff
    d = sub.add_parser("diff", help="classify the operations in ref1..ref2")
    d.add_argument("ref1")
    d.add_argument("ref2")
    d.add_argument("files", nargs="*")
    d.add_argument("--format", choices=["text", "json"], default="text")
    d.add_argument("--patterns", default=None,
                   help="comma-separated operation kinds to include")
    d.add_argument("--risk", choices=["off", "basic", "full"], default="basic")
    d.add_argument("--context", type=int, default=3)
    d.add_argument("--cwd", default=None)
    d.add_argument("--show-evidence", action="store_true")
    d.add_argument("--git-driver-mode", action="store_true",
                   help="(internal) parse positional args as git's "
                        "external-diff 7-tuple "
                        "(path old-file old-hex old-mode "
                        "new-file new-hex new-mode) instead of ref1/ref2")
    d.set_defaults(func=cmd_diff)

    # explain
    e = sub.add_parser("explain", help="classify a single commit")
    e.add_argument("commit")
    e.add_argument("--format", choices=["text", "json"], default="text")
    e.add_argument("--risk", choices=["off", "basic", "full"], default="basic")
    e.add_argument("--show-evidence", action="store_true")
    e.add_argument("--cwd", default=None)
    e.set_defaults(func=cmd_explain)

    # check
    c = sub.add_parser("check", help="malformed-text + parse check on one file")
    c.add_argument("path")
    c.add_argument("--format", choices=["text", "json"], default="text")
    c.set_defaults(func=cmd_check)

    # cache
    ca = sub.add_parser("cache", help="manage the .sextant/cache directory")
    ca.add_argument("action", choices=["clear", "stats"])
    ca.set_defaults(func=cmd_cache)

    # config
    cf = sub.add_parser("config", help="read/write .sextant/config.json")
    cf.add_argument("action", choices=["get", "set", "list"])
    cf.add_argument("key", nargs="?")
    cf.add_argument("value", nargs="?")
    cf.set_defaults(func=cmd_config)

    # register-git-driver
    rg = sub.add_parser("register-git-driver",
                        help="install sextant as a git diff driver")
    rg.add_argument("--scope", choices=["user", "repo"], default="repo")
    rg.add_argument("--uninstall", action="store_true",
                    help="remove a previously-installed sextant driver "
                         "(surgical: only the sextant:managed block + "
                         "diff.sextant.* keys are removed)")
    rg.set_defaults(func=cmd_register_git_driver)

    # web (phase 1C)
    w = sub.add_parser("web", help="launch the local web UI (Preact + esm.sh)")
    w.add_argument("--port", type=int, default=9881,
                   help="port to bind (default: 9881)")
    w.add_argument("--host", default="127.0.0.1",
                   help="host/iface to bind (default: 127.0.0.1)")
    w.add_argument("--open", action="store_true",
                   help="open the URL in the default browser after start")
    w.add_argument("--cwd", default=None,
                   help="project root (default: current working directory)")
    w.set_defaults(func=cmd_web)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    # Force UTF-8 stdout on Windows so `→` etc. don't crash cp1252 terminals.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
