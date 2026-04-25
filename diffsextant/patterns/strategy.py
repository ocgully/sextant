"""Strategy-pattern introduction detector (§3B.1 #1).

Heuristic:
- Before-state contained a dispatching `if/elif` or `switch` chain that
  branches on a type/enum/string value.
- After-state replaces it with a lookup / class hierarchy / map call
  (dict lookup, map access, polymorphic dispatch).
- The count of `elif`/`else if`/`case` arms decreased OR the dispatch
  block disappeared AND a new class was introduced.

Low-ambition version — fires on the clearest signal: a chain of 3+
branches on the same discriminator collapsed into a mapping lookup.
"""
from __future__ import annotations

import re
from typing import Any, List

from diffsextant.ops.base import Classifier, FileChange, Operation, OperationKind


PY_ELIF_RE = re.compile(r"^\s*elif\s+", re.M)
PY_IFKIND_RE = re.compile(r"\bif\s+(\w+)\s*==\s*['\"]?(\w+)['\"]?", re.M)
TS_CASE_RE = re.compile(r"^\s*case\s+['\"]?[\w\.]+['\"]?\s*:", re.M)
SWITCH_RE = re.compile(r"\bswitch\s*\(([^)]+)\)", re.M)


LOOKUP_HINTS = [
    re.compile(r"\w+\[\w+\]"),                  # dict lookup
    re.compile(r"\.get\(\w+(?:,\s*[^)]+)?\)"),  # .get(key)
    re.compile(r"\.apply\(|\.execute\("),       # strategy.method()
]


class StrategyPatternClassifier(Classifier):
    kind = OperationKind.STRATEGY_PATTERN_INTRO
    min_confidence = 0.6

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        before = change.body_before or ""
        after = change.body_after or ""
        if not before or not after or before == after:
            return []

        b_branches = self._count_branches(before, lang)
        a_branches = self._count_branches(after, lang)

        # Need at least 3 branches disappearing
        if b_branches < 3 or a_branches > b_branches - 2:
            return []

        # Need a lookup in after that wasn't in before
        b_lookups = self._lookup_count(before)
        a_lookups = self._lookup_count(after)
        if a_lookups <= b_lookups:
            return []

        conf = 0.70 + min(0.2, (b_branches - a_branches) * 0.05)
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=conf,
            summary=(
                f"strategy pattern introduced: collapsed {b_branches} "
                f"conditional branches into lookup-based dispatch"
            ),
            evidence={
                "branches_before": b_branches,
                "branches_after": a_branches,
                "lookups_before": b_lookups,
                "lookups_after": a_lookups,
            },
        )]

    @staticmethod
    def _count_branches(body: str, lang: str) -> int:
        if lang == "python":
            return len(PY_ELIF_RE.findall(body))
        return len(TS_CASE_RE.findall(body))

    @staticmethod
    def _lookup_count(body: str) -> int:
        return sum(len(p.findall(body)) for p in LOOKUP_HINTS)
