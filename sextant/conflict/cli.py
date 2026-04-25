"""CLI wiring for the conflict subcommands.

Subcommands hosted here:

  sextant conflict <file>                  inspect a conflicted file
  sextant conflict <file> --resolve        walk regions interactively
  sextant register-merge-driver [--scope]  install the git merge driver
  sextant merge-driver %O %A %B %P         driver entrypoint (called by git)

The top-level `sextant/cli.py` registers these by importing
``sextant.conflict.cli.add_subparsers``.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from sextant.conflict.analyze import analyze_file, analyze_three_blobs
from sextant.conflict.render import render_text
from sextant.conflict.types import ConflictFile, ConflictRegion


# ---------------------------------------------------------------------------
# `sextant conflict <file>`
# ---------------------------------------------------------------------------


def cmd_conflict(args) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2

    cf = analyze_file(path, cwd=Path(args.cwd) if args.cwd else None)

    if args.format == "json":
        sys.stdout.write(json.dumps(cf.to_dict(), indent=2) + "\n")
        return 0 if cf.parse_ok else 1

    if args.resolve:
        return _interactive_resolve(path, cf)

    sys.stdout.write(render_text(cf))
    if not cf.regions:
        return 0
    # Exit 1 if any region is UNKNOWN (signals "needs manual review")
    has_unknown = any(r.kind.value == "unknown" for r in cf.regions)
    return 1 if has_unknown or not cf.parse_ok else 0


def _interactive_resolve(path: Path, cf: ConflictFile) -> int:
    """Walk regions one at a time. Apply chosen suggestions, then write
    the file back. ``manual edit`` and ``unknown`` regions are left in
    place (with markers) and the exit code reflects that."""
    if not cf.regions:
        sys.stdout.write("no conflict regions to resolve.\n")
        return 0

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=False)
    # Apply from bottom up so line numbers stay valid
    pending = sorted(cf.regions, key=lambda r: r.line_start, reverse=True)
    unresolved = 0

    for region in pending:
        sys.stdout.write("\n" + render_text(_one_region_file(cf, region)))
        sys.stdout.write("Choose a resolution key (or `s` to skip): ")
        sys.stdout.flush()
        try:
            choice = input().strip()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\nresolution cancelled.\n")
            return 130

        if choice == "s" or choice == "":
            unresolved += 1
            continue
        match = next((s for s in region.suggestions if s.key == choice), None)
        if match is None:
            sys.stdout.write(f"  unknown choice `{choice}`; skipping.\n")
            unresolved += 1
            continue
        if not match.auto_apply or match.body is None:
            sys.stdout.write("  (manual choice — leaving region for editor)\n")
            unresolved += 1
            continue
        # Replace lines [line_start-1 .. line_end-1] with body
        new_body_lines = match.body.splitlines() if match.body else []
        lines[region.line_start - 1: region.line_end] = new_body_lines

    path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""),
                    encoding="utf-8")
    sys.stdout.write(
        f"\nwrote {path}; {unresolved} region(s) left for manual review.\n"
    )
    return 0 if unresolved == 0 else 1


def _one_region_file(cf: ConflictFile, region: ConflictRegion) -> ConflictFile:
    """Build a synthetic single-region ConflictFile for printing."""
    sub = ConflictFile(
        path=cf.path,
        regions=[region],
        provenance=cf.provenance,
        parse_ok=cf.parse_ok,
        parse_error=cf.parse_error,
    )
    return sub


# ---------------------------------------------------------------------------
# `sextant merge-driver %O %A %B %P`
# ---------------------------------------------------------------------------


# The structured comment block that we leave in the file when the merge
# is unresolvable. The exact sentinel `# sextant:merge-summary` lets
# downstream tooling find + strip these on demand.
_SUMMARY_PREFIX = "# sextant:merge-summary"
_SUMMARY_SUFFIX = "# sextant:/merge-summary"


def cmd_merge_driver(args) -> int:
    """Called by git as `sextant merge-driver %O %A %B %P`.

    Per the phase-1D plan:
      1. read the three blobs
      2. classify the change-set
      3. on auto-resolvable kinds: write the resolved file -> %A, exit 0
      4. otherwise: write %A with markers + a structured summary block,
         exit 1 (git keeps the file for the user to fix)
    """
    base_path = Path(args.base)
    ours_path = Path(args.ours)
    theirs_path = Path(args.theirs)

    base = _read(base_path)
    ours = _read(ours_path)
    theirs = _read(theirs_path)

    region = analyze_three_blobs(base, ours, theirs, path=args.path)
    if region is None:
        # No real conflict — nothing to do; leave %A as-is.
        return 0

    auto = _pick_auto_resolution(region)
    if auto is not None:
        ours_path.write_text(auto, encoding="utf-8")
        return 0

    # Unresolvable: write conflict markers + summary into %A, exit 1.
    body = _format_unresolved(region, base, ours, theirs)
    ours_path.write_text(body, encoding="utf-8")
    return 1


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return ""


def _pick_auto_resolution(region: ConflictRegion) -> Optional[str]:
    """Return the body text to write when a safe auto-resolution exists.

    We only auto-resolve concurrent-rename when both sides agree on the
    *target name* (no real disagreement) — which is rare but possible
    after independent refactors. Other cases stay manual to preserve
    operator trust.
    """
    if region.kind.value == "concurrent-rename" and region.ours == region.theirs:
        return region.ours
    return None


def _format_unresolved(region: ConflictRegion, base: str, ours: str, theirs: str) -> str:
    """Compose the file content git will leave in the worktree on
    unresolvable merges: markers + a summary comment block."""
    summary_lines = [
        _SUMMARY_PREFIX,
        f"# kind: {region.kind.value}",
        f"# confidence: {region.confidence:.2f}",
        f"# rationale: {region.rationale}",
    ]
    for sig in region.intent_signals:
        summary_lines.append(f"# intent: {sig}")
    if region.suggestions:
        summary_lines.append("# suggestions:")
        for s in region.suggestions:
            summary_lines.append(f"#   [{s.key}] {s.label}")
    summary_lines.append(_SUMMARY_SUFFIX)
    summary = "\n".join(summary_lines) + "\n"

    out: list[str] = [summary]
    out.append("<<<<<<< ours\n")
    out.append(ours if ours.endswith("\n") else ours + "\n")
    if base:
        out.append("||||||| base\n")
        out.append(base if base.endswith("\n") else base + "\n")
    out.append("=======\n")
    out.append(theirs if theirs.endswith("\n") else theirs + "\n")
    out.append(">>>>>>> theirs\n")
    return "".join(out)


# ---------------------------------------------------------------------------
# `sextant register-merge-driver`
# ---------------------------------------------------------------------------


# Same sentinel scheme as phase 1B's diff driver: a managed block in
# .gitattributes that we own and re-write idempotently.
_GITATTRIBUTES_ENTRIES = [
    "*.py  merge=sextant",
    "*.ts  merge=sextant",
    "*.tsx merge=sextant",
    "*.js  merge=sextant",
    "*.rs  merge=sextant",
    "*.go  merge=sextant",
    "*.md  merge=sextant",
]
_SENTINEL_OPEN = "# sextant:merge-managed"
_SENTINEL_CLOSE = "# sextant:/merge-managed"


def cmd_register_merge_driver(args) -> int:
    cwd = Path.cwd()
    scope_flag = "--global" if args.scope == "user" else "--local"

    try:
        subprocess.run(
            ["git", "config", scope_flag, "merge.sextant.name",
             "Sextant semantic merge driver"],
            check=True, cwd=str(cwd),
        )
        subprocess.run(
            ["git", "config", scope_flag, "merge.sextant.driver",
             "sextant merge-driver %O %A %B %P"],
            check=True, cwd=str(cwd),
        )
        subprocess.run(
            ["git", "config", scope_flag, "merge.sextant.recursive", "binary"],
            check=True, cwd=str(cwd),
        )
    except subprocess.CalledProcessError as e:
        print(f"error: `git config` failed: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print("error: git not installed", file=sys.stderr)
        return 2

    if args.scope == "repo":
        attrs = cwd / ".gitattributes"
        existing = ""
        if attrs.exists():
            existing = attrs.read_text(encoding="utf-8")
        if _SENTINEL_OPEN in existing:
            sys.stdout.write(
                "(.gitattributes already has a sextant merge-managed block — skipped)\n"
            )
        else:
            block = (
                f"\n{_SENTINEL_OPEN}\n"
                + "\n".join(_GITATTRIBUTES_ENTRIES)
                + f"\n{_SENTINEL_CLOSE}\n"
            )
            attrs.write_text(existing + block, encoding="utf-8")
            sys.stdout.write(f"wrote sextant merge-driver block to {attrs}\n")

    sys.stdout.write(
        f"registered `merge.sextant` in git config ({scope_flag}).\n"
        f"git will now route 3-way merges through `sextant merge-driver`.\n"
    )
    return 0


# ---------------------------------------------------------------------------
# parser registration — called from sextant/cli.py
# ---------------------------------------------------------------------------


def add_subparsers(sub: argparse._SubParsersAction) -> None:
    """Register `conflict`, `merge-driver`, `register-merge-driver`."""
    # conflict
    c = sub.add_parser("conflict",
                       help="inspect a conflicted file (3-way classified)")
    c.add_argument("file")
    c.add_argument("--format", choices=["text", "json"], default="text")
    c.add_argument("--resolve", action="store_true",
                   help="walk regions interactively and apply choices")
    c.add_argument("--cwd", default=None)
    c.set_defaults(func=cmd_conflict)

    # merge-driver (called by git itself; not for humans)
    md = sub.add_parser(
        "merge-driver",
        help="git merge driver entrypoint — `sextant merge-driver %%O %%A %%B %%P`",
    )
    md.add_argument("base")
    md.add_argument("ours")
    md.add_argument("theirs")
    md.add_argument("path")
    md.set_defaults(func=cmd_merge_driver)

    # register-merge-driver
    rmd = sub.add_parser(
        "register-merge-driver",
        help="install sextant as a git merge driver",
    )
    rmd.add_argument("--scope", choices=["user", "repo"], default="repo")
    rmd.set_defaults(func=cmd_register_merge_driver)
