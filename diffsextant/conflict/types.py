"""Typed dataclasses for the conflict module.

Kept separate from logic modules so they can be imported without
dragging the parser/classifier code (matters for the merge-driver where
startup time is on the user's critical path).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class ConflictKind(str, Enum):
    """Concurrent-operation taxonomy.

    The five required by the phase-1D spec, plus UNKNOWN as the
    don't-guess fallback. A region carrying ``UNKNOWN`` should never
    auto-resolve.
    """
    CONCURRENT_RENAME = "concurrent-rename"
    CONCURRENT_EDIT   = "concurrent-edit"
    CONCURRENT_MOVE   = "concurrent-move"
    ADD_ADD           = "add-add"
    MODIFY_DELETE     = "modify-delete"
    UNKNOWN           = "unknown"


@dataclass
class Suggestion:
    """One candidate resolution presented to the user."""
    key: str            # single-letter shortcut: 'k', 'u', 'a', 'm', ...
    label: str          # short human label
    detail: str = ""    # extra explanation
    auto_apply: bool = False
    # Replacement text for the entire region body (without markers). When
    # None, this suggestion needs human follow-up (e.g. 'manual edit').
    body: Optional[str] = None


@dataclass
class ConflictRegion:
    """One <<<<<<< / ======= / >>>>>>> block."""
    index: int                       # 1-based order within the file
    line_start: int                  # 1-based; line of <<<<<<<
    line_end: int                    # 1-based; line of >>>>>>>
    ours_label: str = ""             # text after `<<<<<<< `
    theirs_label: str = ""           # text after `>>>>>>> `
    base_label: str = ""             # text after `||||||| ` (diff3 only)
    ours: str = ""                   # body lines, joined w/ \n, no trailing \n
    theirs: str = ""
    base: Optional[str] = None       # populated when diff3 markers present
    kind: ConflictKind = ConflictKind.UNKNOWN
    confidence: float = 0.0          # 0..1
    rationale: str = ""              # free-text human explanation
    intent_signals: List[str] = field(default_factory=list)
    suggestions: List[Suggestion] = field(default_factory=list)

    def risk_bucket(self) -> str:
        """Map (kind, confidence) -> low/medium/high/critical."""
        # add-add and modify-delete are inherently riskier than rename/edit
        if self.kind == ConflictKind.MODIFY_DELETE:
            return "high"
        if self.kind == ConflictKind.ADD_ADD:
            return "medium"
        if self.kind == ConflictKind.UNKNOWN:
            return "high"
        if self.confidence >= 0.75:
            return "low"
        if self.confidence >= 0.5:
            return "medium"
        return "high"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["risk"] = self.risk_bucket()
        return d


@dataclass
class BranchProvenance:
    """Names + shas pulled from .git for the in-flight merge."""
    ours_branch: Optional[str] = None
    ours_sha: Optional[str] = None
    theirs_branch: Optional[str] = None      # from MERGE_HEAD
    theirs_sha: Optional[str] = None
    base_sha: Optional[str] = None           # merge base, if computable
    state: Optional[str] = None              # "merge" | "rebase" | "cherry-pick" | None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConflictFile:
    """The full classified picture for a single conflicted path."""
    path: str
    regions: List[ConflictRegion] = field(default_factory=list)
    provenance: BranchProvenance = field(default_factory=BranchProvenance)
    parse_ok: bool = True
    parse_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "parse_ok": self.parse_ok,
            "parse_error": self.parse_error,
            "provenance": self.provenance.to_dict(),
            "regions": [r.to_dict() for r in self.regions],
        }
