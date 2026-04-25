"""Reorder-statements detector (§3.2 #10).

Same set of top-level statements, same token-multiset, different order.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, List

from diffsextant.ops.base import Classifier, FileChange, Operation, OperationKind


def _statements(body: str, lang: str) -> List[str]:
    # Crude: split on blank-line separators; aligns with most styles.
    chunks = [c.strip() for c in re.split(r"\n\s*\n", body) if c.strip()]
    return chunks


class ReorderStatementsClassifier(Classifier):
    kind = OperationKind.REORDER_STATEMENTS
    min_confidence = 0.65

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang:
            return []
        before = change.body_before or ""
        after = change.body_after or ""
        if before == after or not before or not after:
            return []

        b_stmts = _statements(before, lang)
        a_stmts = _statements(after, lang)
        if not b_stmts or len(b_stmts) < 2 or len(b_stmts) != len(a_stmts):
            return []

        # Same multiset of normalized statements?
        def norm(s: str) -> str:
            return re.sub(r"\s+", " ", s).strip()

        bm = Counter(norm(s) for s in b_stmts)
        am = Counter(norm(s) for s in a_stmts)
        if bm != am:
            return []

        # Actually different order?
        if [norm(s) for s in b_stmts] == [norm(s) for s in a_stmts]:
            return []

        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=0.80,
            summary=f"reordered {len(b_stmts)} top-level statements (same set)",
            evidence={"statement_count": len(b_stmts)},
        )]
