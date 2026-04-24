"""Change-signature + add-method / remove-method (§3.1 #8, #9)."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from sextant.ops.base import Classifier, FileChange, Operation, OperationKind
from sextant.parse import find_nodes, node_text, parse_source


FUNC_TYPES = {
    "python": ["function_definition"],
    "typescript": ["function_declaration", "method_definition"],
    "javascript": ["function_declaration", "method_definition"],
    "rust": ["function_item"],
    "go": ["function_declaration", "method_declaration"],
}


def _func_signature(node, source: bytes) -> Tuple[str, str]:
    name = ""
    try:
        n = node.child_by_field_name("name")
        if n:
            name = node_text(n, source)
    except Exception:
        pass
    # Parameter list: field "parameters" for most grammars; fallback is
    # first children of types "parameters" / "formal_parameters".
    params_node = None
    try:
        params_node = node.child_by_field_name("parameters")
    except Exception:
        pass
    if params_node is None:
        for c in node.children:
            if c.type in ("parameters", "formal_parameters", "parameter_list"):
                params_node = c
                break
    params_text = node_text(params_node, source) if params_node else ""
    return name, params_text.strip()


class ChangeSignatureClassifier(Classifier):
    kind = OperationKind.CHANGE_SIGNATURE
    min_confidence = 0.65

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang or lang not in FUNC_TYPES:
            return []
        before = parse_source(change.body_before, lang)
        after = parse_source(change.body_after, lang)
        if before.tree is None or after.tree is None:
            return []

        b_sigs: Dict[str, str] = {}
        a_sigs: Dict[str, str] = {}
        for t in FUNC_TYPES[lang]:
            for n in find_nodes(before.tree.root_node, t):
                name, params = _func_signature(n, before.source)
                if name:
                    b_sigs[name] = params
            for n in find_nodes(after.tree.root_node, t):
                name, params = _func_signature(n, after.source)
                if name:
                    a_sigs[name] = params

        ops: List[Operation] = []
        for name, a_params in a_sigs.items():
            if name not in b_sigs:
                continue
            b_params = b_sigs[name]
            if a_params == b_params:
                continue
            conf = 0.80
            if ctx is not None:
                conf = min(1.0, conf + ctx.prior_for("change-signature"))
            ops.append(Operation(
                kind=self.kind,
                file=change.path,
                confidence=conf,
                summary=f"changed signature of `{name}`: `{b_params}` → `{a_params}`",
                before=b_params,
                after=a_params,
                evidence={"function": name, "before_params": b_params,
                          "after_params": a_params},
            ))
        return ops
