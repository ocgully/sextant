"""Comment-only + docstring-only detectors (§3.2 #12, #13).

If stripping comments from before + after yields identical bodies, the
change is comment-only. Docstrings are classified separately when the
grammar distinguishes them (Python: module/class/function first string
literal).
"""
from __future__ import annotations

import re
from typing import Any, List

from diffsextant.ops.base import Classifier, FileChange, Operation, OperationKind


# Line-comment + block-comment patterns. Crude but enough for phase 1A.
COMMENT_PATTERNS = {
    "python": [r"#.*?$"],
    "typescript": [r"//.*?$", r"/\*.*?\*/"],
    "tsx": [r"//.*?$", r"/\*.*?\*/"],
    "javascript": [r"//.*?$", r"/\*.*?\*/"],
    "rust": [r"//.*?$", r"/\*.*?\*/"],
    "go": [r"//.*?$", r"/\*.*?\*/"],
    "markdown": [r"<!--.*?-->"],
}


def _strip_comments(source: str, language: str) -> str:
    patterns = COMMENT_PATTERNS.get(language, [])
    for p in patterns:
        source = re.sub(p, "", source, flags=re.M | re.S)
    return source


def _has_meaningful_comment_delta(before: str, after: str, language: str) -> bool:
    """Did comments actually change? Avoids firing on pure-whitespace diffs
    where there were no comments at all."""
    patterns = COMMENT_PATTERNS.get(language, [])
    if not patterns:
        return False
    b_comments = []
    a_comments = []
    for p in patterns:
        b_comments.extend(re.findall(p, before, flags=re.M | re.S))
        a_comments.extend(re.findall(p, after, flags=re.M | re.S))
    return b_comments != a_comments


class CommentOnlyClassifier(Classifier):
    kind = OperationKind.COMMENT_ONLY
    min_confidence = 0.75

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang or lang not in COMMENT_PATTERNS:
            return []
        before = change.body_before or ""
        after = change.body_after or ""
        if before == after or not before or not after:
            return []

        b_stripped = re.sub(r"\s+", " ", _strip_comments(before, lang)).strip()
        a_stripped = re.sub(r"\s+", " ", _strip_comments(after, lang)).strip()

        if b_stripped != a_stripped:
            return []

        if not _has_meaningful_comment_delta(before, after, lang):
            return []

        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=0.92,
            summary="comments added/removed/edited; code body unchanged",
            evidence={"byte_delta": len(after) - len(before)},
        )]


class DocstringOnlyClassifier(Classifier):
    """Python-specific: first string literal in a module / class / function."""
    kind = OperationKind.DOCSTRING_ONLY
    min_confidence = 0.75

    DOCSTRING_RE = re.compile(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')')

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        if change.language != "python":
            return []
        before = change.body_before or ""
        after = change.body_after or ""
        if before == after or not before or not after:
            return []
        # Strip docstrings. If stripping yields identical bodies AND the
        # docstring list actually changed, classify as docstring-only.
        b_docs = self.DOCSTRING_RE.findall(before)
        a_docs = self.DOCSTRING_RE.findall(after)
        if b_docs == a_docs:
            return []
        b_stripped = re.sub(r"\s+", " ", self.DOCSTRING_RE.sub("", before)).strip()
        a_stripped = re.sub(r"\s+", " ", self.DOCSTRING_RE.sub("", after)).strip()
        if b_stripped != a_stripped:
            return []
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=0.92,
            summary="docstrings changed; code body unchanged",
            evidence={"docstring_count_before": len(b_docs),
                      "docstring_count_after": len(a_docs)},
        )]
