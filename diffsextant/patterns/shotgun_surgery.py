"""Shotgun-surgery anti-pattern (§3B.3 #19).

Cross-file detector: a single logical change is spread across many
files. Heuristic proxy: the same identifier changed in > N files, or
> N files touched when the commit message describes a single logical
intent.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, List

from diffsextant.ops.base import FileChange, Operation, OperationKind


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Thresholds
FILE_COUNT_THRESHOLD = 5
IDENT_OVERLAP_THRESHOLD = 3  # same identifier changed in N+ files


def detect_shotgun_surgery(changes: List[FileChange], ctx: Any) -> List[Operation]:
    """Emit zero or one shotgun-surgery operation spanning all affected
    files. Because it's a whole-diff observation, there's at most one.
    """
    changed = [c for c in changes if (c.body_before or "") != (c.body_after or "")]
    if len(changed) < FILE_COUNT_THRESHOLD:
        return []

    # Identify identifiers present in each change delta (crude: idents in
    # before symmetric-diff idents in after).
    per_file_delta_idents = []
    for ch in changed:
        before_idents = set(IDENT_RE.findall(ch.body_before or ""))
        after_idents = set(IDENT_RE.findall(ch.body_after or ""))
        per_file_delta_idents.append(before_idents.symmetric_difference(after_idents))

    # Aggregate: how many files each identifier was "involved in"
    global_counter: Counter = Counter()
    for idents in per_file_delta_idents:
        global_counter.update(idents)

    shared = [(name, cnt) for name, cnt in global_counter.items()
              if cnt >= IDENT_OVERLAP_THRESHOLD]

    if not shared:
        return []

    shared.sort(key=lambda kv: -kv[1])
    top = shared[:5]

    return [Operation(
        kind=OperationKind.SHOTGUN_SURGERY,
        file=changed[0].path,  # primary; the full list lives in related_files
        confidence=0.75,
        summary=(
            f"shotgun-surgery warning: {len(changed)} files touch shared "
            f"identifiers: {', '.join(f'{n} ({c})' for n, c in top)}"
        ),
        related_files=[c.path for c in changed],
        evidence={
            "file_count": len(changed),
            "shared_identifiers": [{"name": n, "files": c} for n, c in top],
        },
    )]
