"""High-level convenience wrappers used by the CLI + web server.

``analyze_file(path)`` parses a working file, classifies every region,
attaches suggestions, and reads branch provenance from .git. One call
returns the full picture for rendering.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sextant.conflict.classifier import classify_region, classify_three_blobs
from sextant.conflict.parser import parse_conflict_file
from sextant.conflict.provenance import read_branch_provenance
from sextant.conflict.suggest import suggest_for_region
from sextant.conflict.types import ConflictFile, ConflictRegion


def analyze_file(path: Path | str, *, cwd: Optional[Path] = None) -> ConflictFile:
    """Parse + classify + suggest for a single file."""
    p = Path(path)
    cf = parse_conflict_file(p)
    repo_cwd = Path(cwd) if cwd else (p.parent if p.parent.exists() else Path.cwd())
    cf.provenance = read_branch_provenance(repo_cwd)
    for region in cf.regions:
        classify_region(region)
        suggest_for_region(region)
    return cf


def analyze_three_blobs(
    base: str, ours: str, theirs: str, path: str = "<blob>"
) -> Optional[ConflictRegion]:
    """For the merge driver: classify + suggest in one step. Returns
    None when the three blobs have a trivial resolution (no conflict)."""
    region = classify_three_blobs(base, ours, theirs, path=path)
    if region is None:
        return None
    suggest_for_region(region)
    return region
