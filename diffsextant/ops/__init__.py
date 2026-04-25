"""Operation classifiers — each module detects one operation kind.

Classifiers run in a deterministic order; the first that fires with
confidence >= its threshold claims the affected region. Plain-edit is
the fallback. Classifiers may co-exist when they affect disjoint regions.
"""
from diffsextant.ops.base import (
    Operation,
    OperationKind,
    Confidence,
    FileChange,
    Classifier,
    bucket_confidence,
)

__all__ = [
    "Operation",
    "OperationKind",
    "Confidence",
    "FileChange",
    "Classifier",
    "bucket_confidence",
]
