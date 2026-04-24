"""Shared types for the operation classifier pipeline.

Every Operation is a structured record with a kind, a scope, evidence,
and a confidence score bucketed into low/medium/high. Classifiers emit
Operations; the renderer consumes them.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class OperationKind(str, Enum):
    # §3.1 structural
    RENAME_SYMBOL = "rename-symbol"
    EXTRACT_FUNCTION = "extract-function"
    INLINE_FUNCTION = "inline-function"
    MOVE_SYMBOL = "move-symbol"
    MOVE_FILE = "move-file"
    SPLIT_FILE = "split-file"
    MERGE_FILES = "merge-files"
    CHANGE_SIGNATURE = "change-signature"
    ADD_METHOD = "add-method"
    REMOVE_METHOD = "remove-method"

    # §3.2 block-level
    REORDER_STATEMENTS = "reorder-statements"
    REFORMAT = "reformat"
    COMMENT_ONLY = "comment-only"
    DOCSTRING_ONLY = "docstring-only"
    LINT_FIX = "lint-fix"

    # §3.3 control flow
    INVERT_CONDITION = "invert-condition"
    CONVERT_LOOP_FORM = "convert-loop-form"
    EXTRACT_CONDITION = "extract-condition"

    # §3.4 imports
    ADD_IMPORT = "add-import"
    REMOVE_IMPORT = "remove-import"
    REORDER_IMPORTS = "reorder-imports"

    # §3.5 tests
    ADD_TEST = "add-test"
    REMOVE_TEST = "remove-test"
    RENAME_TEST = "rename-test"

    # §3.6 fallback / special
    PLAIN_EDIT = "plain-edit"
    MALFORMED = "malformed"

    # §3B patterns
    STRATEGY_PATTERN_INTRO = "strategy-pattern-intro"
    GOD_CLASS_FORMING = "god-class-forming"
    SHOTGUN_SURGERY = "shotgun-surgery"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def bucket_confidence(score: float) -> Confidence:
    """Per §3: >0.9 high, 0.7-0.9 medium, <0.7 low."""
    if score > 0.9:
        return Confidence.HIGH
    if score >= 0.7:
        return Confidence.MEDIUM
    return Confidence.LOW


@dataclass
class FileChange:
    """One file's before/after bodies + path info."""
    path_before: Optional[str]
    path_after: Optional[str]
    body_before: str
    body_after: str
    language: Optional[str] = None

    @property
    def path(self) -> str:
        return self.path_after or self.path_before or "<unknown>"

    @property
    def is_new(self) -> bool:
        return self.path_before is None

    @property
    def is_deleted(self) -> bool:
        return self.path_after is None

    @property
    def is_renamed(self) -> bool:
        return (
            self.path_before is not None
            and self.path_after is not None
            and self.path_before != self.path_after
        )


@dataclass
class Operation:
    """A single classified operation. The unit of Sextant's output."""
    kind: OperationKind
    file: str                     # primary file (after-path if renamed)
    confidence: float             # 0.0 - 1.0
    summary: str                  # one-line human description
    before: Optional[str] = None  # representative before-snippet
    after: Optional[str] = None   # representative after-snippet
    evidence: Dict[str, Any] = field(default_factory=dict)
    # extra files touched (e.g. move-file: both paths; shotgun-surgery: all files)
    related_files: List[str] = field(default_factory=list)
    risk: Optional[Dict[str, Any]] = None

    @property
    def confidence_bucket(self) -> Confidence:
        return bucket_confidence(self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["confidence_bucket"] = self.confidence_bucket.value
        return d


class Classifier:
    """Base class for operation classifiers. Subclasses implement
    `classify(change, ctx) -> list[Operation]`. Ctx carries the parsed
    ASTs + the git context so each classifier doesn't re-parse.
    """

    kind: OperationKind = OperationKind.PLAIN_EDIT
    #: Confidence floor for emitting the op at all. Everything below is
    #: discarded so we don't pollute the output with weak guesses.
    min_confidence: float = 0.5

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:  # pragma: no cover - abstract
        raise NotImplementedError

    # -- helpers shared by subclasses --

    @staticmethod
    def _snippet(body: str, max_lines: int = 6) -> str:
        lines = body.splitlines()
        if len(lines) <= max_lines:
            return body
        return "\n".join(lines[:max_lines]) + f"\n  ... ({len(lines) - max_lines} more lines)"
