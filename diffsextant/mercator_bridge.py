"""OPTIONAL Mercator integration (§4.4).

When `.mercator/` exists in the cwd, call `mercator query ...` for
richer risk signals. Phase 1A treats Mercator as optional: if absent
or failing, we degrade silently and risk.py's local heuristics win.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def is_available(cwd: Path) -> bool:
    """True iff `.mercator/` exists AND a `mercator` CLI is on PATH."""
    return (cwd / ".mercator").exists() and shutil.which("mercator") is not None


def _query(cwd: Path, *args: str) -> Optional[Any]:
    try:
        r = subprocess.run(
            ["mercator", "query", *args, "--format", "json"],
            cwd=str(cwd), capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def public_api_impact(cwd: Path, system: str, symbol: str) -> Optional[bool]:
    if not is_available(cwd):
        return None
    data = _query(cwd, "contract", system)
    if not data:
        return None
    exports = data.get("exports") or []
    return any(symbol == e.get("name") for e in exports if isinstance(e, dict))


def call_sites(cwd: Path, symbol: str) -> Optional[int]:
    if not is_available(cwd):
        return None
    data = _query(cwd, "symbol", symbol)
    if not data:
        return None
    return len(data.get("call_sites") or [])


def system_for_path(cwd: Path, path: str) -> Optional[str]:
    if not is_available(cwd):
        return None
    data = _query(cwd, "touches", path)
    if not data:
        return None
    if isinstance(data, dict):
        return data.get("system")
    return None
