"""Sextant — semantic-operation diff classifier.

Reads diffs as operations (rename, extract, move, reformat, ...) rather
than raw line deltas. Phase 1A ships the deterministic classifier + CLI +
git-context + standalone risk. LLM residual, GUI, and merge-driver UX
land in later sub-phases.

Public surface:

    from sextant import classify_diff, Operation, OperationKind
    from sextant.parse import parse_source, detect_language
    from sextant.risk import assess

Agents should interact via the `sextant` CLI; the library is for embedders.
"""
from __future__ import annotations

__version__ = "0.5.0"

from sextant.ops.base import (
    Operation,
    OperationKind,
    Confidence,
    FileChange,
)

__all__ = [
    "__version__",
    "Operation",
    "OperationKind",
    "Confidence",
    "FileChange",
    "classify_diff",
]


def classify_diff(*args, **kwargs):
    """Top-level entry point. Lazy import to avoid dragging tree-sitter
    at `import sextant`.
    """
    from sextant.tree_delta import classify_diff as _impl
    return _impl(*args, **kwargs)
