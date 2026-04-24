"""Move-file + move-symbol detectors (§3.1 #4, #5).

`move-file`: path changed AND body normalized matches (allow small
patch — we accept near-identical bodies, confirmed by content-hash
prefix similarity).

`move-symbol`: a function/class that was in file A's `before` is
present in file B's `after`, identical body.

This module's `move-symbol` runs at the diff level, not per-file; the
diff-level driver invokes `MoveSymbolCrossFile` separately.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from sextant.ops.base import Classifier, FileChange, Operation, OperationKind
from sextant.parse import find_nodes, node_text, parse_source


class MoveFileClassifier(Classifier):
    """Per-file classifier: fires when the path changed."""
    kind = OperationKind.MOVE_FILE
    min_confidence = 0.7

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        if not change.is_renamed:
            return []

        # Similarity — identical bytes is the strong case; near-identical
        # (allow a 10% edit) is the weaker case.
        before = change.body_before or ""
        after = change.body_after or ""
        a = re.sub(r"\s+", " ", before).strip()
        b = re.sub(r"\s+", " ", after).strip()

        if a == b:
            conf = 0.95
            verdict = "identical"
        else:
            # cheap similarity score: longest common prefix + suffix / max
            lcp = 0
            for ch_a, ch_b in zip(a, b):
                if ch_a != ch_b:
                    break
                lcp += 1
            lcs = 0
            for ch_a, ch_b in zip(reversed(a), reversed(b)):
                if ch_a != ch_b:
                    break
                lcs += 1
            max_len = max(len(a), len(b), 1)
            sim = (lcp + lcs) / max_len
            if sim < 0.80:
                return []  # body changed too much for a pure move
            conf = 0.70 + 0.2 * sim
            verdict = f"near-identical sim={sim:.2f}"

        if ctx is not None:
            conf = min(1.0, conf + ctx.prior_for("move-file"))

        return [Operation(
            kind=self.kind,
            file=change.path_after or "",
            confidence=conf,
            summary=f"moved `{change.path_before}` → `{change.path_after}` ({verdict})",
            related_files=[change.path_before] if change.path_before else [],
            evidence={
                "from": change.path_before,
                "to": change.path_after,
                "verdict": verdict,
            },
        )]


# -- cross-file move-symbol (invoked by the driver, not the per-file loop) --

FUNC_TYPES_BY_LANG = {
    "python": ["function_definition", "class_definition"],
    "typescript": ["function_declaration", "class_declaration"],
    "javascript": ["function_declaration", "class_declaration"],
    "rust": ["function_item", "struct_item", "enum_item"],
    "go": ["function_declaration", "method_declaration"],
}


def _symbol_bodies(parse, lang: str) -> Dict[str, str]:
    """Map {symbol-name: normalized-body} for every top-level definition."""
    types = FUNC_TYPES_BY_LANG.get(lang, [])
    if not types or parse.tree is None:
        return {}
    out: Dict[str, str] = {}
    for t in types:
        for n in find_nodes(parse.tree.root_node, t):
            try:
                name_node = n.child_by_field_name("name")
            except Exception:
                name_node = None
            if name_node is None:
                continue
            name = node_text(name_node, parse.source)
            body = node_text(n, parse.source)
            out[name] = re.sub(r"\s+", " ", body).strip()
    return out


def detect_move_symbols(changes: List[FileChange], ctx: Any) -> List[Operation]:
    """Cross-file detection. Symbol present in A's before + B's after
    with identical body + absent from A's after = move-symbol."""
    ops: List[Operation] = []

    # Index: symbol-body-hash -> list of (path, direction, name)
    # simpler: for each pair (removed in A, added in B), compare bodies.
    removed: List[Tuple[str, str, str]] = []  # (file, name, body)
    added: List[Tuple[str, str, str]] = []

    for ch in changes:
        lang = ch.language
        if not lang or lang not in FUNC_TYPES_BY_LANG:
            continue
        before = parse_source(ch.body_before, lang)
        after = parse_source(ch.body_after, lang)
        if before.tree is None and after.tree is None:
            continue
        before_syms = _symbol_bodies(before, lang) if before.tree else {}
        after_syms = _symbol_bodies(after, lang) if after.tree else {}
        for name, body in before_syms.items():
            if name not in after_syms:
                removed.append((ch.path_before or ch.path, name, body))
        for name, body in after_syms.items():
            if name not in before_syms:
                added.append((ch.path_after or ch.path, name, body))

    for r_file, r_name, r_body in removed:
        for a_file, a_name, a_body in added:
            if a_file == r_file:
                continue
            if r_body == a_body and r_name == a_name and len(r_body) > 20:
                conf = 0.85
                if ctx is not None:
                    conf = min(1.0, conf + ctx.prior_for("move-symbol"))
                ops.append(Operation(
                    kind=OperationKind.MOVE_SYMBOL,
                    file=a_file,
                    confidence=conf,
                    summary=f"moved `{a_name}` from `{r_file}` → `{a_file}`",
                    related_files=[r_file],
                    evidence={
                        "symbol": a_name,
                        "from_file": r_file,
                        "to_file": a_file,
                    },
                ))
                break
    return ops
