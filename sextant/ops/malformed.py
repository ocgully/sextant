"""Malformed-text detection (§3C).

Short-circuits the pipeline: a malformed file is tagged prominently and
NOT classified as a normal operation. Signals:

- Merge-conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
- Parse yields ERROR nodes covering > 20% of the file
- Mixed line endings
- Zero-width / bidi / suspicious Unicode
- Truncation heuristics (unterminated strings / blocks at EOF)
- Binary content where text is expected
"""
from __future__ import annotations

import re
from typing import Any, List, Optional

from sextant.ops.base import Classifier, Confidence, FileChange, Operation, OperationKind
from sextant.parse import parse_source


CONFLICT_START = re.compile(r"^<{7} ", re.M)
CONFLICT_MIDDLE = re.compile(r"^={7}$", re.M)
CONFLICT_END = re.compile(r"^>{7} ", re.M)


# U+200B ZERO WIDTH SPACE through related; U+2066-U+2069 bidi overrides.
SUSPICIOUS_UNICODE = re.compile(
    "[​-‏‪-‮⁠-⁤⁦-⁩﻿]"
)


def detect(source: str, language: Optional[str] = None) -> Optional[dict]:
    """Return a signals dict if `source` is malformed, else None."""
    signals: List[str] = []
    details: dict = {}

    if not source:
        return None

    # Binary probe: non-utf8 decodable bytes or NULs
    if "\x00" in source:
        signals.append("binary-content")

    # Conflict markers
    has_start = CONFLICT_START.search(source) is not None
    has_mid = CONFLICT_MIDDLE.search(source) is not None
    has_end = CONFLICT_END.search(source) is not None
    if has_start and has_mid and has_end:
        signals.append("merge-conflict-markers")
        details["conflict_markers"] = True

    # Suspicious unicode
    m = SUSPICIOUS_UNICODE.search(source)
    if m:
        signals.append("suspicious-unicode")
        details["first_suspicious_codepoint"] = hex(ord(m.group(0)))

    # Mixed line endings — both CRLF and bare LF present
    if "\r\n" in source and re.search(r"(?<!\r)\n", source):
        signals.append("mixed-line-endings")

    # Parse-error ratio
    if language:
        parse = parse_source(source, language)
        if parse.tree is not None and parse.error_ratio > 0.20:
            signals.append("parse-error-ratio-exceeded")
            details["error_ratio"] = round(parse.error_ratio, 3)
            details["error_count"] = parse.error_count

    # Truncation: file ends with obvious mid-statement forms. We only
    # fire on the LAST line so we don't mis-flag normal code that
    # happens to contain a string literal.
    stripped = source.rstrip()
    if stripped:
        last_line = stripped.splitlines()[-1] if stripped else ""
        unterminated_patterns = [
            # odd count of unescaped " quotes in the last line AND the
            # line ends without terminator punctuation -> likely truncated.
            (r"\{$", "unterminated-block"),
            (r"\($", "unterminated-paren"),
        ]
        for pat, name in unterminated_patterns:
            if re.search(pat, last_line.rstrip()):
                signals.append(name)
                break
        # simple odd-quote check on the last line (escape-naive but enough
        # to catch an obvious truncation mid-literal)
        if last_line.count('"') % 2 == 1 and not last_line.rstrip().endswith(";"):
            # only flag if the line doesn't look like normal end-of-statement
            if not re.search(r'[)\]\};]\s*$', last_line):
                signals.append("unterminated-string")

    if not signals:
        return None
    return {"signals": signals, "details": details}


class MalformedClassifier(Classifier):
    kind = OperationKind.MALFORMED
    min_confidence = 0.9  # always high-confidence when it fires

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        # Check AFTER body — malformation in the "new" state is what matters
        body = change.body_after if change.body_after else change.body_before
        if not body:
            return []
        sig = detect(body, language=change.language)
        if sig is None:
            return []
        return [Operation(
            kind=self.kind,
            file=change.path,
            confidence=0.98,
            summary=f"MALFORMED: {', '.join(sig['signals'])}",
            after=body[:400],
            evidence=sig,
        )]
