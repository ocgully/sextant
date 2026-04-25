"""Phase 1D — three-way conflict tooling.

Public surface:

    from diffsextant.conflict import (
        ConflictRegion, ConflictFile, ConflictKind, Suggestion,
        parse_conflict_file, classify_region, suggest_for_region,
        analyze_file, analyze_three_blobs,
        BranchProvenance, read_branch_provenance,
    )

Conflicts are parsed by *region* (a single ``<<<<<<< / ======= / >>>>>>>``
block) and classified into one of:

    * concurrent-rename   — both sides renamed the same symbol differently
    * concurrent-edit     — both sides edited overlapping content
    * concurrent-move     — both sides moved/relocated the same block
    * add-add             — neither side existed at base; both sides added
    * modify-delete       — one side modified; the other deleted

The classifier is intentionally heuristic — high precision, modest
recall. Each region carries a confidence bucket + a free-text rationale.
Unrecognised regions fall back to ``UNKNOWN`` rather than guessing.
"""
from __future__ import annotations

from diffsextant.conflict.types import (
    ConflictKind,
    ConflictRegion,
    ConflictFile,
    Suggestion,
    BranchProvenance,
)
from diffsextant.conflict.parser import parse_conflict_file, parse_conflict_text
from diffsextant.conflict.classifier import classify_region, classify_three_blobs
from diffsextant.conflict.suggest import suggest_for_region
from diffsextant.conflict.provenance import read_branch_provenance
from diffsextant.conflict.analyze import analyze_file, analyze_three_blobs

__all__ = [
    "ConflictKind",
    "ConflictRegion",
    "ConflictFile",
    "Suggestion",
    "BranchProvenance",
    "parse_conflict_file",
    "parse_conflict_text",
    "classify_region",
    "classify_three_blobs",
    "suggest_for_region",
    "read_branch_provenance",
    "analyze_file",
    "analyze_three_blobs",
]
