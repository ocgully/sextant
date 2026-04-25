"""Git diff-driver registration for sextant.

Phase 1B (HW-0056). Installs / uninstalls sextant as a git diff driver
in either user (~/.gitconfig) or repo (.git/config + .gitattributes)
scope, using sentinel-marked blocks so uninstall is surgical.

## Architecture

Two mutations per install:

  1. **git config** — sets `diff.sextant.command` (and friends) at the
     chosen scope. We track our own keys via a managed-key list; the
     uninstall walks that list and `git config --unset` each entry.
     Git config has no native block syntax, so the "sentinel block" for
     config is the explicit list of keys this module owns.

  2. **.gitattributes** (repo-scope only) — appends a sentinel-bracketed
     block:

         # >>> sextant:managed (do not edit) >>>
         *.py  diff=sextant
         *.ts  diff=sextant
         ...
         # <<< sextant:managed <<<

     Re-running install detects the sentinel and leaves the block alone.
     Uninstall strips exactly that block (and any leading blank line we
     added) and leaves user-authored content untouched.

User-scope installs do NOT touch any .gitattributes — git only consults
attribute files in the worktree (or `core.attributesFile`) and we don't
want to silently take that over. Users wanting global attributes should
configure `core.attributesFile` themselves.

## Git external-diff protocol

When `[diff "sextant"] command = ...` is set and a path matches
`diff=sextant` in .gitattributes, git invokes the command with seven
positional arguments:

    cmd  path  old-file  old-hex  old-mode  new-file  new-hex  new-mode

`old-file` / `new-file` are temp-file paths to the blob contents on disk.
Sextant's diff command was originally written to take ref1/ref2 (git
revs); the `--git-driver-mode` flag rebinds that command's argv shape to
accept the 7 positional driver args instead, classify the on-disk
before/after pair, and render to stdout.

## CLI extension snippet

The argparse subcommand was scaffolded in phase 1A; in phase 1B `cli.py`
delegates to this module:

    # in sextant/cli.py
    def cmd_register_git_driver(args) -> int:
        from diffsextant.git_driver import install, uninstall
        return uninstall(scope=args.scope) if args.uninstall \
               else install(scope=args.scope)

    # parser
    rg = sub.add_parser("register-git-driver",
                        help="install sextant as a git diff driver")
    rg.add_argument("--scope", choices=["user", "repo"], default="repo")
    rg.add_argument("--uninstall", action="store_true",
                    help="remove a previously-installed sextant driver")
    rg.set_defaults(func=cmd_register_git_driver)

And `diffsextant diff` gains the protocol bridge:

    d.add_argument("--git-driver-mode", action="store_true",
                   help="(internal) parse argv as git's external-diff "
                        "7-positional protocol instead of ref1/ref2")
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------


SENTINEL_OPEN = "# >>> sextant:managed (do not edit) >>>"
SENTINEL_CLOSE = "# <<< sextant:managed <<<"

# .gitattributes patterns. Repo-scope only.
DEFAULT_ATTR_PATTERNS: Tuple[str, ...] = (
    "*.py",
    "*.ts",
    "*.tsx",
    "*.js",
    "*.rs",
    "*.go",
    "*.md",
)

# git config keys we own. Uninstall walks this list and `--unset` each.
MANAGED_CONFIG_KEYS: Tuple[str, ...] = (
    "diff.sextant.command",
    "diff.sextant.binary",
    "diff.sextant.cachetextconv",
)

# The command git invokes. `--format text` is the human-friendly one
# (json is reserved for explicit CLI use). The driver-mode flag tells
# `diffsextant diff` to parse positional args as git's 7-tuple.
DRIVER_COMMAND = "diffsextant diff --git-driver-mode --format text"


# ---------------------------------------------------------------------------
# scope helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    name: str            # "user" | "repo"
    config_flag: str     # "--global" | "--local"
    touches_attrs: bool  # True for repo, False for user


SCOPE_USER = Scope(name="user", config_flag="--global", touches_attrs=False)
SCOPE_REPO = Scope(name="repo", config_flag="--local", touches_attrs=True)


def _scope(name: str) -> Scope:
    if name == "user":
        return SCOPE_USER
    if name == "repo":
        return SCOPE_REPO
    raise ValueError(f"unknown scope: {name!r} (expected 'user' or 'repo')")


# ---------------------------------------------------------------------------
# git config helpers
# ---------------------------------------------------------------------------


def _git(args: List[str], *, cwd: Optional[Path] = None,
         check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def _git_config_get(scope: Scope, key: str, *, cwd: Path) -> Optional[str]:
    """Return the value or None if unset. Never raises on absent."""
    proc = _git(["config", scope.config_flag, "--get", key],
                cwd=cwd, check=False)
    if proc.returncode == 0:
        return proc.stdout.strip()
    return None


def _git_config_set(scope: Scope, key: str, value: str, *, cwd: Path) -> None:
    _git(["config", scope.config_flag, key, value], cwd=cwd, check=True)


def _git_config_unset(scope: Scope, key: str, *, cwd: Path) -> bool:
    """Returns True if a key was actually unset, False if it was already absent."""
    proc = _git(["config", scope.config_flag, "--unset", key],
                cwd=cwd, check=False)
    # exit 5 = key not present; exit 0 = unset OK; anything else is an error
    if proc.returncode == 0:
        return True
    if proc.returncode == 5:
        return False
    raise RuntimeError(f"git config --unset {key} failed: {proc.stderr.strip()}")


def _ensure_repo(cwd: Path) -> None:
    proc = _git(["rev-parse", "--git-dir"], cwd=cwd, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{cwd} is not a git worktree (cannot install repo-scope driver)"
        )


# ---------------------------------------------------------------------------
# .gitattributes helpers
# ---------------------------------------------------------------------------


def _build_attr_block(patterns: Tuple[str, ...]) -> str:
    width = max(len(p) for p in patterns) if patterns else 0
    body = "\n".join(f"{p.ljust(width)}  diff=sextant" for p in patterns)
    return f"{SENTINEL_OPEN}\n{body}\n{SENTINEL_CLOSE}\n"


_BLOCK_RE = re.compile(
    re.escape(SENTINEL_OPEN) + r"\n.*?\n" + re.escape(SENTINEL_CLOSE) + r"\n?",
    re.DOTALL,
)


def _has_managed_block(text: str) -> bool:
    return SENTINEL_OPEN in text and SENTINEL_CLOSE in text


def _strip_managed_block(text: str) -> str:
    """Remove the sentinel-marked block. Collapse stray triple-newlines
    we may have left behind so the file doesn't grow blank lines on
    repeated install/uninstall cycles."""
    new = _BLOCK_RE.sub("", text)
    new = re.sub(r"\n{3,}", "\n\n", new)
    return new


def _append_attr_block(existing: str, block: str) -> str:
    if not existing:
        return block
    if not existing.endswith("\n"):
        existing += "\n"
    # Separate user content from our block with one blank line for readability.
    if not existing.endswith("\n\n"):
        existing += "\n"
    return existing + block


# ---------------------------------------------------------------------------
# public install / uninstall
# ---------------------------------------------------------------------------


def install(*, scope: str = "repo",
            cwd: Optional[Path] = None,
            patterns: Tuple[str, ...] = DEFAULT_ATTR_PATTERNS,
            stream=sys.stdout) -> int:
    """Install sextant as a git diff driver. Idempotent.

    Returns the CLI-style exit code (0 = OK, non-zero = error).
    """
    scope_obj = _scope(scope)
    cwd = (cwd or Path.cwd()).resolve()
    if scope_obj.touches_attrs:
        try:
            _ensure_repo(cwd)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

    # 1. git config
    existing_cmd = _git_config_get(scope_obj, "diff.sextant.command", cwd=cwd)
    if existing_cmd == DRIVER_COMMAND:
        stream.write(
            f"git config ({scope_obj.config_flag}) already has "
            f"diff.sextant.command — skipped\n"
        )
    else:
        _git_config_set(scope_obj, "diff.sextant.command", DRIVER_COMMAND, cwd=cwd)
        _git_config_set(scope_obj, "diff.sextant.binary", "false", cwd=cwd)
        _git_config_set(scope_obj, "diff.sextant.cachetextconv", "false", cwd=cwd)
        stream.write(
            f"registered diff.sextant in git config ({scope_obj.config_flag})\n"
        )

    # 2. .gitattributes (repo-scope only)
    if scope_obj.touches_attrs:
        attrs_path = cwd / ".gitattributes"
        existing = attrs_path.read_text(encoding="utf-8") if attrs_path.exists() else ""
        if _has_managed_block(existing):
            stream.write(
                f".gitattributes already has a sextant:managed block "
                f"at {attrs_path} — skipped\n"
            )
        else:
            block = _build_attr_block(patterns)
            new_text = _append_attr_block(existing, block)
            attrs_path.write_text(new_text, encoding="utf-8")
            stream.write(f"wrote sextant:managed block to {attrs_path}\n")

    stream.write(
        "git diff on matching files now routes through sextant.\n"
    )
    return 0


def uninstall(*, scope: str = "repo",
              cwd: Optional[Path] = None,
              stream=sys.stdout) -> int:
    """Remove a previously-installed diffsextant diff driver. Idempotent."""
    scope_obj = _scope(scope)
    cwd = (cwd or Path.cwd()).resolve()
    if scope_obj.touches_attrs:
        try:
            _ensure_repo(cwd)
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

    # 1. git config
    unset_any = False
    for key in MANAGED_CONFIG_KEYS:
        if _git_config_unset(scope_obj, key, cwd=cwd):
            unset_any = True
    if unset_any:
        stream.write(
            f"removed diff.sextant.* from git config ({scope_obj.config_flag})\n"
        )
    else:
        stream.write(
            f"no diff.sextant.* keys found in git config "
            f"({scope_obj.config_flag}) — already clean\n"
        )

    # 2. .gitattributes
    if scope_obj.touches_attrs:
        attrs_path = cwd / ".gitattributes"
        if not attrs_path.exists():
            stream.write("no .gitattributes file — already clean\n")
        else:
            existing = attrs_path.read_text(encoding="utf-8")
            if not _has_managed_block(existing):
                stream.write(
                    f"{attrs_path} has no sextant:managed block — already clean\n"
                )
            else:
                stripped = _strip_managed_block(existing)
                # If the file is now empty (only whitespace), remove it.
                if stripped.strip() == "":
                    attrs_path.unlink()
                    stream.write(f"removed empty {attrs_path}\n")
                else:
                    attrs_path.write_text(stripped, encoding="utf-8")
                    stream.write(f"stripped sextant:managed block from {attrs_path}\n")

    return 0


# ---------------------------------------------------------------------------
# external-diff protocol bridge
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GitDriverInvocation:
    """The 7 positional args git passes to a diff driver.

    https://git-scm.com/docs/gitattributes#_defining_an_external_diff_driver
    """
    path: str
    old_file: str
    old_hex: str
    old_mode: str
    new_file: str
    new_hex: str
    new_mode: str

    @classmethod
    def from_argv(cls, argv: List[str]) -> "GitDriverInvocation":
        if len(argv) < 7:
            raise ValueError(
                f"--git-driver-mode expects 7 positional args "
                f"(path old-file old-hex old-mode new-file new-hex new-mode); "
                f"got {len(argv)}"
            )
        return cls(*argv[:7])


def render_driver_invocation(inv: GitDriverInvocation,
                             *, fmt: str = "text",
                             stream=sys.stdout) -> int:
    """Classify the on-disk old/new pair git handed us, then render.

    Reuses the standard sextant per-file classifier pipeline. Unlike
    `diffsextant diff <ref1> <ref2>`, there's no git range here — git has
    already materialised both blobs as temp files. We build a single
    `FileChange` from those bytes and run the same pipeline used in
    `tree_delta.classify_diff`.
    """
    from diffsextant.ops.base import FileChange, Operation, OperationKind
    from diffsextant.parse import detect_language
    from diffsextant.tree_delta import DiffResult, _per_file_classifiers
    from diffsextant.render import render_json, render_text

    def _read(p: str) -> str:
        # git uses /dev/null cross-platform for the "doesn't exist" side.
        # Treat absent / empty-path files as empty body.
        if not p or p in ("/dev/null", "nul", "NUL"):
            return ""
        try:
            return Path(p).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    body_before = _read(inv.old_file)
    body_after = _read(inv.new_file)

    change = FileChange(
        path_before=inv.path,
        path_after=inv.path,
        body_before=body_before,
        body_after=body_after,
        language=detect_language(inv.path),
    )

    classifiers = _per_file_classifiers()
    file_ops: List[Operation] = []
    warnings: List[str] = []
    if change.body_before != change.body_after:
        malformed_hit = False
        for cls in classifiers:
            try:
                ops = cls.classify(change, None)
            except Exception as e:
                warnings.append(
                    f"classifier {cls.__class__.__name__} failed: {e}"
                )
                continue
            for op in ops:
                if op.confidence < cls.min_confidence:
                    continue
                file_ops.append(op)
                if op.kind == OperationKind.MALFORMED:
                    malformed_hit = True
            if malformed_hit:
                break
        if not file_ops:
            file_ops.append(Operation(
                kind=OperationKind.PLAIN_EDIT,
                file=inv.path,
                confidence=0.50,
                summary=f"unclassified text change in `{inv.path}`",
                evidence={
                    "before_bytes": len(body_before),
                    "after_bytes": len(body_after),
                },
            ))

    result = DiffResult(
        operations=file_ops,
        changes=[change],
        git_context=None,
        warnings=warnings,
    )
    if fmt == "json":
        stream.write(render_json(result) + "\n")
    else:
        stream.write(render_text(result, threshold=0.0))
    return 0
