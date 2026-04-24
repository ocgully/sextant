"""Cache management for .sextant/cache/.

Phase 1A uses this only as a scaffolding; actual AST + classification
caching hooks are stubbed so later phases can plug them in without
changing the public CLI.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional


def cache_dir(cwd: Path) -> Path:
    return cwd / ".sextant" / "cache"


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
