"""Parse conflict markers in a working file into structured regions.

Recognised formats:

    <<<<<<< OURS_LABEL
    ours body
    =======
    theirs body
    >>>>>>> THEIRS_LABEL

    <<<<<<< OURS_LABEL
    ours body
    ||||||| BASE_LABEL          # diff3 / merge.conflictStyle = diff3
    base body
    =======
    theirs body
    >>>>>>> THEIRS_LABEL

The parser is intentionally tolerant — a stray `=======` at the start
of a line outside a conflict block is ignored unless we're already
inside an open `<<<<<<<` block. Unterminated blocks produce a
``ConflictFile`` with ``parse_ok=False`` rather than raising.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from diffsextant.conflict.types import ConflictFile, ConflictRegion


# Markers — we accept >=7 chars to match git's behaviour (it requires
# exactly 7 by default but some tools pad). We keep the strict 7-char
# default for safety and only relax on read.
_MIN_MARKER_LEN = 7


def _is_marker(line: str, ch: str) -> Tuple[bool, str]:
    """Return (is_marker, label_text). Marker line looks like::

        <<<<<<< label here\n
    """
    if not line:
        return False, ""
    # Strip a single trailing newline if present
    body = line.rstrip("\n").rstrip("\r")
    if len(body) < _MIN_MARKER_LEN:
        return False, ""
    if not body.startswith(ch * _MIN_MARKER_LEN):
        return False, ""
    # Must be all `ch` until whitespace or end
    i = 0
    while i < len(body) and body[i] == ch:
        i += 1
    if i < _MIN_MARKER_LEN:
        return False, ""
    rest = body[i:]
    label = rest.lstrip(" \t")
    return True, label


def parse_conflict_text(text: str, path: str = "<text>") -> ConflictFile:
    """Parse a conflict-marker-bearing string. Never raises."""
    cf = ConflictFile(path=path)
    lines = text.splitlines(keepends=False)

    # State machine
    state = "scan"            # scan | ours | base | theirs
    cur: Optional[ConflictRegion] = None
    ours_buf: List[str] = []
    base_buf: List[str] = []
    theirs_buf: List[str] = []
    region_idx = 0

    def _finalise(cur: ConflictRegion, end_line_1b: int) -> None:
        cur.ours = "\n".join(ours_buf)
        cur.theirs = "\n".join(theirs_buf)
        if base_buf or state == "base" or cur.base_label:
            cur.base = "\n".join(base_buf) if base_buf else ""
        cur.line_end = end_line_1b
        cf.regions.append(cur)

    for i, raw in enumerate(lines):
        ln = i + 1  # 1-based
        is_lt, ours_label = _is_marker(raw, "<")
        is_eq, _          = _is_marker(raw, "=")
        is_gt, theirs_lbl = _is_marker(raw, ">")
        is_pipe, base_lbl = _is_marker(raw, "|")

        if state == "scan":
            if is_lt:
                region_idx += 1
                cur = ConflictRegion(
                    index=region_idx, line_start=ln, line_end=ln,
                    ours_label=ours_label,
                )
                ours_buf, base_buf, theirs_buf = [], [], []
                state = "ours"
            # else: regular line outside a conflict — ignore
            continue

        if state == "ours":
            if is_pipe:
                cur.base_label = base_lbl
                state = "base"
                continue
            if is_eq:
                state = "theirs"
                continue
            if is_gt:
                # Malformed: missing ======= separator. Treat as theirs-end.
                cur.theirs_label = theirs_lbl
                _finalise(cur, ln)
                cf.parse_ok = False
                cf.parse_error = (
                    cf.parse_error
                    or f"region #{cur.index}: missing `=======` separator at line {ln}"
                )
                cur = None
                state = "scan"
                continue
            if is_lt:
                # Nested <<<<<<<: bail out of this region
                cf.parse_ok = False
                cf.parse_error = (
                    cf.parse_error
                    or f"nested `<<<<<<<` at line {ln} inside region #{cur.index}"
                )
                # Treat current as broken; restart on this marker
                _finalise(cur, ln - 1)
                region_idx += 1
                cur = ConflictRegion(
                    index=region_idx, line_start=ln, line_end=ln,
                    ours_label=ours_label,
                )
                ours_buf, base_buf, theirs_buf = [], [], []
                state = "ours"
                continue
            ours_buf.append(raw)
            continue

        if state == "base":
            if is_eq:
                state = "theirs"
                continue
            if is_gt or is_lt:
                cf.parse_ok = False
                cf.parse_error = cf.parse_error or (
                    f"region #{cur.index}: bad marker order in base section at line {ln}"
                )
                _finalise(cur, ln)
                cur = None
                state = "scan"
                continue
            base_buf.append(raw)
            continue

        if state == "theirs":
            if is_gt:
                cur.theirs_label = theirs_lbl
                _finalise(cur, ln)
                cur = None
                state = "scan"
                continue
            if is_lt or is_eq or is_pipe:
                cf.parse_ok = False
                cf.parse_error = cf.parse_error or (
                    f"region #{cur.index}: stray marker at line {ln} inside theirs"
                )
                _finalise(cur, ln)
                cur = None
                state = "scan"
                continue
            theirs_buf.append(raw)
            continue

    # Unterminated region at EOF
    if cur is not None:
        cf.parse_ok = False
        cf.parse_error = cf.parse_error or (
            f"region #{cur.index}: unterminated conflict block (no `>>>>>>>`)"
        )
        _finalise(cur, len(lines))

    return cf


def parse_conflict_file(path: Path | str) -> ConflictFile:
    """Read `path` from disk and parse it. The returned ``ConflictFile``
    has ``parse_ok=False`` if I/O failed."""
    p = Path(path)
    cf = ConflictFile(path=str(p))
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        cf.parse_ok = False
        cf.parse_error = f"no such file: {p}"
        return cf
    except OSError as e:
        cf.parse_ok = False
        cf.parse_error = f"cannot read {p}: {e}"
        return cf
    out = parse_conflict_text(text, path=str(p))
    return out
