"""Invert-condition detector (§3.3 #15).

A simple pattern: `if (X) { A } else { B }` -> `if (!X) { B } else { A }`.
We detect by finding if-else blocks where the condition is negated and
the branches are swapped. Text-level heuristic keyed on common negation
patterns across our five languages.
"""
from __future__ import annotations

import re
from typing import Any, List

from diffsextant.ops.base import Classifier, FileChange, Operation, OperationKind


# Capture classic `if <cond>:` / `if (<cond>) {` patterns per language.
IF_PATTERNS = {
    "python": re.compile(r"\bif\s+([^\n:]+?)\s*:", re.M),
    "typescript": re.compile(r"\bif\s*\(([^)]+)\)", re.M),
    "javascript": re.compile(r"\bif\s*\(([^)]+)\)", re.M),
    "tsx": re.compile(r"\bif\s*\(([^)]+)\)", re.M),
    "rust": re.compile(r"\bif\s+([^{\n]+?)\s*\{", re.M),
    "go": re.compile(r"\bif\s+([^{\n]+?)\s*\{", re.M),
}


def _is_inversion(a: str, b: str) -> bool:
    """Is `b` the logical inverse of `a`?"""
    a = a.strip()
    b = b.strip()
    # common negation markers
    candidates = [
        (f"not {a}", b),
        (f"!{a}", b),
        (f"!({a})", b),
        (a, f"not {b}"),
        (a, f"!{b}"),
        (a, f"!({b})"),
    ]
    for x, y in candidates:
        if re.sub(r"\s+", "", x) == re.sub(r"\s+", "", y):
            return True
    # swap == / !=
    if "==" in a and a.replace("==", "!=") == b:
        return True
    if "!=" in a and a.replace("!=", "==") == b:
        return True
    return False


class InvertConditionClassifier(Classifier):
    kind = OperationKind.INVERT_CONDITION
    min_confidence = 0.65

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang or lang not in IF_PATTERNS:
            return []
        before = change.body_before or ""
        after = change.body_after or ""
        if before == after:
            return []

        pat = IF_PATTERNS[lang]
        b_conds = pat.findall(before)
        a_conds = pat.findall(after)
        if len(b_conds) != len(a_conds):
            return []

        ops: List[Operation] = []
        for b, a in zip(b_conds, a_conds):
            if b != a and _is_inversion(b, a):
                conf = 0.82
                if ctx is not None:
                    conf = min(1.0, conf + ctx.prior_for("invert-condition"))
                ops.append(Operation(
                    kind=self.kind,
                    file=change.path,
                    confidence=conf,
                    summary=f"inverted condition: `{b.strip()[:60]}` → `{a.strip()[:60]}`",
                    before=b.strip(),
                    after=a.strip(),
                    evidence={"before_cond": b.strip(), "after_cond": a.strip()},
                ))
        return ops
