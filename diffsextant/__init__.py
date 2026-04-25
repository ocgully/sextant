"""diffsextant — semantic-operation diff classifier (formerly `sextant`).

Renamed in April 2026. The legacy `sextant` CLI entry point is kept as
a deprecation alias that prints a stderr warning and forwards to
`diffsextant`.

Reads diffs as operations (rename, extract, move, reformat, ...) rather
than raw line deltas. Phase 1A ships the deterministic classifier + CLI +
git-context + standalone risk. LLM residual, GUI, and merge-driver UX
land in later sub-phases.

Public surface:

    from diffsextant import classify_diff, Operation, OperationKind
    from diffsextant.parse import parse_source, detect_language
    from diffsextant.risk import assess

Agents should interact via the `diffsextant` CLI; the library is for
embedders.
"""
from __future__ import annotations

__version__ = "0.6.0"

from diffsextant.ops.base import (
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
    at `import diffsextant`.
    """
    from diffsextant.tree_delta import classify_diff as _impl
    return _impl(*args, **kwargs)
