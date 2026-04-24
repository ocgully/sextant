"""Test-file operations: add-test / remove-test / rename-test (§3.5).

Detection: the file path matches `test_*`, `*_test.*`, `*.test.*`, or
`tests/` directory prefix. Each test function counts independently.
"""
from __future__ import annotations

import re
from typing import Any, List

from sextant.ops.base import Classifier, FileChange, Operation, OperationKind


TEST_PATH_RE = re.compile(r"(^|/)tests?/|(^|/)test_[^/]+|_test\.[^/]+$|\.test\.[^/]+$|_spec\.[^/]+$")


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH_RE.search(path))


TEST_FUNC_PATTERNS = {
    "python": re.compile(r"^\s*def\s+(test_\w+)\s*\(", re.M),
    "typescript": re.compile(r"""(?:\btest|\bit|\bdescribe)\s*\(\s*['"]([^'"]+)['"]""", re.M),
    "javascript": re.compile(r"""(?:\btest|\bit|\bdescribe)\s*\(\s*['"]([^'"]+)['"]""", re.M),
    "rust": re.compile(r"#\[test\]\s*(?:pub\s+)?fn\s+(\w+)", re.M),
    "go": re.compile(r"^\s*func\s+(Test\w+)\s*\(", re.M),
}


def _test_names(body: str, lang: str) -> List[str]:
    pat = TEST_FUNC_PATTERNS.get(lang)
    if pat is None:
        return []
    return pat.findall(body)


class AddTestClassifier(Classifier):
    kind = OperationKind.ADD_TEST
    min_confidence = 0.75

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        if not is_test_path(change.path):
            return []
        lang = change.language
        before = _test_names(change.body_before or "", lang) if lang else []
        after = _test_names(change.body_after or "", lang) if lang else []
        added = [t for t in after if t not in before]
        if not added:
            return []
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=0.90,
            summary=f"added {len(added)} test(s): {', '.join(added[:3])}" + (
                " ..." if len(added) > 3 else ""),
            evidence={"added": added},
        )]


class RemoveTestClassifier(Classifier):
    kind = OperationKind.REMOVE_TEST
    min_confidence = 0.75

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        if not is_test_path(change.path):
            return []
        lang = change.language
        before = _test_names(change.body_before or "", lang) if lang else []
        after = _test_names(change.body_after or "", lang) if lang else []
        removed = [t for t in before if t not in after]
        if not removed:
            return []
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=0.90,
            summary=f"removed {len(removed)} test(s): {', '.join(removed[:3])}" + (
                " ..." if len(removed) > 3 else ""),
            evidence={"removed": removed},
        )]
