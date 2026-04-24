"""Import operations: add-import / remove-import / reorder-imports (§3.4).

Per-language regex matchers. We avoid tree-sitter here — the regex
surface is stable across the 5 phase-1A languages and the classifier
is cheap enough to run on every diff.
"""
from __future__ import annotations

import re
from typing import Any, List, Set, Tuple

from sextant.ops.base import Classifier, FileChange, Operation, OperationKind


IMPORT_PATTERNS = {
    "python": re.compile(
        r"^[ \t]*(?:from[ \t]+[\w\.]+[ \t]+import[ \t]+[\w\.\*\,\(\)\s]+?|import[ \t]+[\w\.\,\s]+?)$",
        re.M,
    ),
    "typescript": re.compile(r"^[ \t]*import[ \t]+[^\n]+from[ \t]+['\"][^'\"]+['\"];?[ \t]*$", re.M),
    "tsx": re.compile(r"^[ \t]*import[ \t]+[^\n]+from[ \t]+['\"][^'\"]+['\"];?[ \t]*$", re.M),
    "javascript": re.compile(r"^[ \t]*import[ \t]+[^\n]+from[ \t]+['\"][^'\"]+['\"];?[ \t]*$", re.M),
    "rust": re.compile(r"^[ \t]*use[ \t]+[^;\n]+;[ \t]*$", re.M),
    "go": re.compile(r"^[ \t]*import[ \t]+(?:\"[^\"]+\"|\([^)]*\))", re.M),
}


def _extract_imports(body: str, lang: str) -> List[str]:
    pat = IMPORT_PATTERNS.get(lang)
    if pat is None:
        return []
    return [line.strip() for line in pat.findall(body)]


class AddImportClassifier(Classifier):
    kind = OperationKind.ADD_IMPORT
    min_confidence = 0.8

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang or lang not in IMPORT_PATTERNS:
            return []
        before = _extract_imports(change.body_before or "", lang)
        after = _extract_imports(change.body_after or "", lang)
        added = [i for i in after if i not in before]
        if not added:
            return []
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=0.93,
            summary=f"added {len(added)} import(s): {', '.join(added[:3])}" + (
                " ..." if len(added) > 3 else ""),
            evidence={"added": added},
        )]


class RemoveImportClassifier(Classifier):
    kind = OperationKind.REMOVE_IMPORT
    min_confidence = 0.8

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang or lang not in IMPORT_PATTERNS:
            return []
        before = _extract_imports(change.body_before or "", lang)
        after = _extract_imports(change.body_after or "", lang)
        removed = [i for i in before if i not in after]
        if not removed:
            return []
        conf = 0.93
        if ctx is not None:
            conf = min(1.0, conf + ctx.prior_for("remove-import"))
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=conf,
            summary=f"removed {len(removed)} import(s): {', '.join(removed[:3])}" + (
                " ..." if len(removed) > 3 else ""),
            evidence={"removed": removed},
        )]


class ReorderImportsClassifier(Classifier):
    kind = OperationKind.REORDER_IMPORTS
    min_confidence = 0.75

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang or lang not in IMPORT_PATTERNS:
            return []
        before = _extract_imports(change.body_before or "", lang)
        after = _extract_imports(change.body_after or "", lang)
        if not before or len(before) < 2:
            return []
        if set(before) != set(after):
            return []
        if before == after:
            return []
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=0.88,
            summary=f"reordered {len(before)} imports (same set)",
            evidence={"import_count": len(before)},
        )]
