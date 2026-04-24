"""Reformat + lint-fix detectors (§3.2 #11, #14).

Reformat = whitespace/brace changes with no token-level change.
Lint-fix = formatter signatures detected (black / prettier / rustfmt /
gofmt / ruff --fix).

Both short-circuit: if every identifier-sequence + literal-sequence is
identical, it's a pure reformat. Lint-fix adds the additional signal of
commit-msg / tool-signature presence.
"""
from __future__ import annotations

import re
from typing import Any, List

from sextant.ops.base import Classifier, FileChange, Operation, OperationKind


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?|\"[^\"]*\"|'[^']*'")


def _token_sequence(body: str) -> tuple:
    return tuple(TOKEN_RE.findall(body))


class ReformatClassifier(Classifier):
    kind = OperationKind.REFORMAT
    min_confidence = 0.75

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        before = change.body_before or ""
        after = change.body_after or ""
        if not before or not after or before == after:
            return []

        # Same token sequence (identifiers + literals + numbers) = reformat.
        if _token_sequence(before) != _token_sequence(after):
            return []

        # Require non-trivial file: at least ~20 bytes AND at least 3
        # tokens. A one-char whitespace tweak isn't really "reformat".
        if len(before) < 20 and len(after) < 20:
            return []
        if len(_token_sequence(before)) < 3:
            return []

        conf = 0.90
        if ctx is not None:
            conf = min(1.0, conf + ctx.prior_for("reformat"))
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=conf,
            summary="whitespace/formatting changes only (tokens unchanged)",
            evidence={
                "before_bytes": len(before),
                "after_bytes": len(after),
                "byte_delta": len(after) - len(before),
            },
        )]


class LintFixClassifier(Classifier):
    """Fires when the commit message / body signature suggests a linter did
    this. It's a stricter specialization of reformat."""
    kind = OperationKind.LINT_FIX
    min_confidence = 0.75

    FORMATTER_HINTS = re.compile(
        r"\b(black|prettier|rustfmt|gofmt|ruff\s+--fix|eslint\s+--fix|autopep8|yapf|clang-format)\b",
        re.I,
    )

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        before = change.body_before or ""
        after = change.body_after or ""
        if not before or not after or before == after:
            return []
        if _token_sequence(before) != _token_sequence(after):
            return []

        # Must have a formatter hint in the commit message
        if ctx is None or not ctx.commit_messages:
            return []
        corpus = " ".join(m.get("body", "") for m in ctx.commit_messages)
        m = self.FORMATTER_HINTS.search(corpus)
        if not m:
            return []
        conf = 0.90
        conf = min(1.0, conf + ctx.prior_for("lint-fix"))
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=conf,
            summary=f"lint-fix: `{m.group(0)}` signature in commit message",
            evidence={
                "formatter": m.group(0),
                "byte_delta": len(after) - len(before),
            },
        )]
