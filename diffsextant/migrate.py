"""One-shot migration from legacy `.sextant/` storage to `.diffsextant/`.

Consumer projects that adopted the tool pre-rename have a `.sextant/`
directory at the repo root. This module implements:

    diffsextant migrate-from-sextant [--dry-run]

which renames the directory to `.diffsextant/`, rewrites any internal
references that hard-code `.sextant/` in stored JSON/MD files, and
updates a project-root `.claudeignore` so agents that are told to skip
the storage dir keep doing so.

Idempotent: if `.diffsextant/` already exists (and `.sextant/` does
not), the migration is a no-op. If both exist, we refuse to clobber.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional


LEGACY_DIR = ".sextant"
NEW_DIR = ".diffsextant"


def migrate(project_root: Path, *, dry_run: bool = False) -> dict:
    """Rename `.sextant/` -> `.diffsextant/` and rewrite internal refs.

    Returns a result dict with `status` in
    {"migrated", "already-migrated", "noop", "dry-run"} plus a `rewrites`
    list describing each file touched (or that would be touched).
    """
    legacy = project_root / LEGACY_DIR
    new = project_root / NEW_DIR

    if new.is_dir() and not legacy.is_dir():
        return {"status": "already-migrated", "from": str(legacy), "to": str(new), "rewrites": []}

    if not legacy.is_dir():
        return {"status": "noop", "from": str(legacy), "to": str(new), "rewrites": []}

    if new.is_dir() and legacy.is_dir():
        raise RuntimeError(
            f"both {legacy} and {new} exist — refusing to clobber. "
            f"Move or delete one before re-running `diffsextant migrate-from-sextant`."
        )

    rewrites: List[str] = []
    rewrite_plan: List[tuple] = []
    for p in legacy.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".json", ".jsonl", ".md", ".yaml", ".yml"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new_text = text.replace(".sextant/", ".diffsextant/")
        if new_text != text:
            rel = p.relative_to(legacy).as_posix()
            rewrites.append(rel)
            rewrite_plan.append((p, new_text))

    ci_path = project_root / ".claudeignore"
    ci_rewrite: Optional[str] = None
    if ci_path.is_file():
        try:
            ci_text = ci_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            ci_text = None
        if ci_text is not None:
            new_ci = []
            changed = False
            for line in ci_text.splitlines():
                s = line.strip()
                if s in (".sextant/", ".sextant", ".sextant/*", ".sextant/**"):
                    new_ci.append(line.replace(".sextant", ".diffsextant"))
                    changed = True
                else:
                    new_ci.append(line)
            if changed:
                ci_rewrite = "\n".join(new_ci) + ("\n" if ci_text.endswith("\n") else "")
                rewrites.append(".claudeignore")

    if dry_run:
        return {
            "status": "dry-run",
            "from": str(legacy),
            "to": str(new),
            "rewrites": rewrites,
        }

    for p, new_text in rewrite_plan:
        p.write_text(new_text, encoding="utf-8")

    shutil.move(str(legacy), str(new))

    if ci_rewrite is not None:
        ci_path.write_text(ci_rewrite, encoding="utf-8")

    return {
        "status": "migrated",
        "from": str(legacy),
        "to": str(new),
        "rewrites": rewrites,
    }
