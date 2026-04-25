"""Cache management for .diffsextant/cache/ (legacy: .sextant/cache/).

Phase 1A uses this only as a scaffolding; actual AST + classification
caching hooks are stubbed so later phases can plug them in without
changing the public CLI.

Dual-read: prefers `.diffsextant/`, falls back to `.sextant/` for
backwards compat. Run `diffsextant migrate-from-sextant` to rename in
place.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional


STORAGE_DIR = ".diffsextant"
LEGACY_STORAGE_DIR = ".sextant"


def storage_dir(cwd: Path) -> Path:
    """Return the on-disk storage dir, preferring `.diffsextant/` but
    falling back to `.sextant/` if only the legacy dir exists. New
    projects always get `.diffsextant/`."""
    new = cwd / STORAGE_DIR
    if new.is_dir():
        return new
    legacy = cwd / LEGACY_STORAGE_DIR
    if legacy.is_dir():
        return legacy
    return new


def cache_dir(cwd: Path) -> Path:
    return storage_dir(cwd) / "cache"


def ensure_cache_dir(cwd: Path) -> Path:
    d = cache_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    (d / "ast").mkdir(exist_ok=True)
    (d / "classify").mkdir(exist_ok=True)
    return d


def stats(cwd: Path) -> Dict[str, Any]:
    d = cache_dir(cwd)
    if not d.exists():
        return {"exists": False, "path": str(d)}
    sizes = {"ast": 0, "classify": 0}
    counts = {"ast": 0, "classify": 0}
    for sub in ("ast", "classify"):
        p = d / sub
        if not p.exists():
            continue
        for f in p.rglob("*"):
            if f.is_file():
                sizes[sub] += f.stat().st_size
                counts[sub] += 1
    return {"exists": True, "path": str(d), "counts": counts, "bytes": sizes}


def clear(cwd: Path) -> bool:
    d = cache_dir(cwd)
    if d.exists():
        shutil.rmtree(d)
        return True
    return False
