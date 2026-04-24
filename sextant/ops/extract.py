"""Extract-function detector (§3.1 #2).

Heuristic: a new function appeared in `after` that didn't exist in
`before`, AND its body is a contiguous sub-sequence (modulo param
rename) of a function that shrank. Precise AST matching would use
Gumtree — we use a simplified normalized-substring approach that works
for the common cases.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from sextant.ops.base import Classifier, FileChange, Operation, OperationKind
from sextant.parse import find_nodes, node_text, parse_source


FUNC_TYPES = {
    "python": ["function_definition"],
    "typescript": ["function_declaration", "method_definition", "arrow_function"],
    "tsx": ["function_declaration", "method_definition"],
    "javascript": ["function_declaration", "method_definition"],
    "rust": ["function_item"],
    "go": ["function_declaration", "method_declaration"],
}


def _func_name(node, source: bytes) -> str:
    try:
        nn = node.child_by_field_name("name")
        if nn:
            return node_text(nn, source)
    except Exception:
        pass
    for c in node.children:
        if c.type in ("identifier", "type_identifier", "property_identifier"):
            return node_text(c, source)
    return ""


def _func_body(node, source: bytes) -> str:
    try:
        body = node.child_by_field_name("body")
        if body:
            return node_text(body, source)
    except Exception:
        pass
    return node_text(node, source)


def _normalize(s: str) -> str:
    # collapse whitespace; strip identifiers' leading/trailing; keep tokens
    return re.sub(r"\s+", " ", s).strip()


class ExtractFunctionClassifier(Classifier):
    kind = OperationKind.EXTRACT_FUNCTION
    min_confidence = 0.65

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang or lang not in FUNC_TYPES:
            return []

        before = parse_source(change.body_before, lang)
        after = parse_source(change.body_after, lang)
        if before.tree is None or after.tree is None:
            return []

        types = FUNC_TYPES[lang]
        before_funcs: Dict[str, Tuple[str, int]] = {}
        for t in types:
            for n in find_nodes(before.tree.root_node, t):
                nm = _func_name(n, before.source)
                if nm:
                    before_funcs[nm] = (_func_body(n, before.source),
                                        n.end_byte - n.start_byte)

        after_funcs: Dict[str, Tuple[str, int]] = {}
        for t in types:
            for n in find_nodes(after.tree.root_node, t):
                nm = _func_name(n, after.source)
                if nm:
                    after_funcs[nm] = (_func_body(n, after.source),
                                       n.end_byte - n.start_byte)

        new_funcs = {k: v for k, v in after_funcs.items() if k not in before_funcs}
        ops: List[Operation] = []

        for new_name, (new_body, _size) in new_funcs.items():
            normalized_new = _normalize(new_body)
            if len(normalized_new) < 20:
                continue  # trivial one-liner, not an extract
            # Look for a function that SHRANK in the after version and whose
            # before-body contained `normalized_new` (modulo whitespace).
            for shared in before_funcs.keys() & after_funcs.keys():
                before_body, before_size = before_funcs[shared]
                after_body, after_size = after_funcs[shared]
                if after_size >= before_size:
                    continue
                normalized_before = _normalize(before_body)
                normalized_after = _normalize(after_body)
                # before body contained the extracted body's statements
                if len(normalized_new) > 0 and normalized_new[:80] in normalized_before:
                    # and the after body no longer contains them
                    if normalized_new[:80] not in normalized_after:
                        # confirm after body now calls the new function
                        if re.search(rf"\b{re.escape(new_name)}\b", after_body):
                            conf = 0.80
                            if ctx is not None:
                                conf = min(1.0, conf + ctx.prior_for("extract-function"))
                            ops.append(Operation(
                                kind=self.kind,
                                file=change.path,
                                confidence=conf,
                                summary=f"extracted `{new_name}()` from `{shared}()`",
                                before=before_body[:300],
                                after=new_body[:300],
                                evidence={
                                    "new_function": new_name,
                                    "source_function": shared,
                                    "shrink_bytes": before_size - after_size,
                                },
                            ))
                            break
        return ops
