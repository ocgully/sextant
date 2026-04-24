"""OPTIONAL Pedia integration (§4.5).

When `.pedia/` exists, surface "this change touches spec-cited blocks"
hints. Phase 1A is best-effort: missing pedia → silent skip.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def is_available(cwd: Path) -> bool:
    return (cwd / ".pedia").exists() and shutil.which("pedia") is not None


def consumers(cwd: Path, path: str, anchor: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    if not is_available(cwd):
        return None
    args = ["pedia", "query", "consumers", path, "--format", "json"]
    if anchor:
        args.extend(["--slice", anchor])
    try:
        r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=15,
                           encoding="utf-8", errors="replace")
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("consumers") or []
    return None
