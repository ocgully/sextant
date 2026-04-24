"""God-class-forming anti-pattern (§3B.3 #16).

Fires when a class gained substantially more methods / lines in the
diff's after-state than it had in before. Thresholds:

- Method count increase: +3 methods in one diff OR total >= 20 AFTER
- LOC increase: +200 LOC in one class OR total >= 500 AFTER
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from sextant.ops.base import Classifier, FileChange, Operation, OperationKind
from sextant.parse import find_nodes, node_text, parse_source


CLASS_TYPES = {
    "python": "class_definition",
    "typescript": "class_declaration",
    "javascript": "class_declaration",
    "rust": None,  # Rust doesn't have "classes"; treat impl-blocks as close analogue
    "go": None,
}

METHOD_TYPES = {
    "python": "function_definition",
    "typescript": "method_definition",
    "javascript": "method_definition",
}


def _class_stats(parse, lang: str) -> Dict[str, Dict[str, int]]:
    ct = CLASS_TYPES.get(lang)
    mt = METHOD_TYPES.get(lang)
    if not ct or not mt or parse.tree is None:
        return {}
    out: Dict[str, Dict[str, int]] = {}
    for cnode in find_nodes(parse.tree.root_node, ct):
        # class name
        name = ""
        try:
            nn = cnode.child_by_field_name("name")
            if nn:
                name = node_text(nn, parse.source)
        except Exception:
            pass
        if not name:
            continue
        methods = find_nodes(cnode, mt)
        loc = node_text(cnode, parse.source).count("\n") + 1
        out[name] = {"methods": len(methods), "loc": loc}
    return out


class GodClassClassifier(Classifier):
    kind = OperationKind.GOD_CLASS_FORMING
    min_confidence = 0.6

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang or lang not in CLASS_TYPES or CLASS_TYPES[lang] is None:
            return []
        before = parse_source(change.body_before, lang)
        after = parse_source(change.body_after, lang)
        if after.tree is None:
            return []
        before_stats = _class_stats(before, lang)
        after_stats = _class_stats(after, lang)

        ops: List[Operation] = []
        for name, a in after_stats.items():
            b = before_stats.get(name, {"methods": 0, "loc": 0})
            d_methods = a["methods"] - b["methods"]
            d_loc = a["loc"] - b["loc"]
            reasons = []
            if a["methods"] >= 20 or (d_methods >= 3 and a["methods"] >= 12):
                reasons.append(f"{a['methods']} methods (+{d_methods})")
            if a["loc"] >= 500 or (d_loc >= 200 and a["loc"] >= 300):
                reasons.append(f"{a['loc']} LOC (+{d_loc})")
            if not reasons:
                continue
            conf = 0.70 + min(0.2, d_methods * 0.02 + d_loc * 0.0005)
            ops.append(Operation(
                kind=self.kind,
                file=change.path,
                confidence=min(0.95, conf),
                summary=f"god-class warning: `{name}` — {'; '.join(reasons)}",
                evidence={
                    "class": name,
                    "methods_before": b["methods"],
                    "methods_after": a["methods"],
                    "loc_before": b["loc"],
                    "loc_after": a["loc"],
                },
            ))
        return ops
