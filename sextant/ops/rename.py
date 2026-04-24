"""Rename-symbol detector (§3.1 #1).

Deterministic algorithm, language-agnostic wrapper around tree-sitter:

1. Parse before + after
2. Collect "named defining" nodes — function / class / variable names —
   per language, using tree-sitter node types.
3. Compare defined-name sets. Every name that disappears on one side
   but whose replacement on the other side is in the SAME structural
   position is a candidate rename.
4. Confirm: the bodies of the two structures must match modulo the name
   substitution. (Normalized by replacing the old name with the new.)
5. Emit one rename-symbol operation per confirmed pair.

If tree-sitter isn't available OR the language isn't supported, fall
back to a line-diff heuristic: same-line count, single identifier
swapped consistently across > N occurrences.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from sextant.ops.base import Classifier, FileChange, Operation, OperationKind
from sextant.parse import ParseResult, find_nodes, node_text, parse_source, walk


# Per-language: (container-node-type, name-child-field-or-type, language-scope)
# "name-child-field" uses tree-sitter field lookup where available; fallback
# is a type-based first-child scan.
RENAME_TARGETS: Dict[str, List[Tuple[str, str]]] = {
    "python": [
        ("function_definition", "name"),
        ("class_definition", "name"),
    ],
    "typescript": [
        ("function_declaration", "name"),
        ("class_declaration", "name"),
        ("method_definition", "name"),
        ("variable_declarator", "name"),
    ],
    "tsx": [
        ("function_declaration", "name"),
        ("class_declaration", "name"),
    ],
    "javascript": [
        ("function_declaration", "name"),
        ("class_declaration", "name"),
        ("method_definition", "name"),
        ("variable_declarator", "name"),
    ],
    "rust": [
        ("function_item", "name"),
        ("struct_item", "name"),
        ("enum_item", "name"),
        ("trait_item", "name"),
    ],
    "go": [
        ("function_declaration", "name"),
        ("method_declaration", "name"),
        ("type_declaration", "name"),
    ],
}


IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _name_of(node, field: str, source: bytes) -> Optional[str]:
    """Extract a name from a defining node. Tries tree-sitter field first,
    then falls back to first-child-identifier."""
    try:
        name_node = node.child_by_field_name(field)
    except Exception:
        name_node = None
    if name_node is None:
        # fallback: first identifier-typed child
        for c in node.children:
            if c.type in ("identifier", "type_identifier", "property_identifier"):
                name_node = c
                break
    if name_node is None:
        return None
    return node_text(name_node, source)


def _collect_definitions(parse: ParseResult, language: str) -> List[Tuple[str, str, Any]]:
    """Return [(container_type, name, node), ...] for every rename target."""
    targets = RENAME_TARGETS.get(language, [])
    if not targets or parse.tree is None:
        return []
    out = []
    for ct, field in targets:
        for n in find_nodes(parse.tree.root_node, ct):
            name = _name_of(n, field, parse.source)
            if name:
                out.append((ct, name, n))
    return out


def _body_of(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _normalized_body(body: str, old_name: str, new_name: str) -> str:
    """Replace whole-word occurrences of `old_name` with `new_name`, then
    strip all whitespace so trivial reformats don't break the match."""
    replaced = re.sub(rf"\b{re.escape(old_name)}\b", new_name, body)
    return re.sub(r"\s+", "", replaced)


def _count_identifier(body: str, name: str) -> int:
    return len(re.findall(rf"\b{re.escape(name)}\b", body))


class RenameSymbolClassifier(Classifier):
    kind = OperationKind.RENAME_SYMBOL
    min_confidence = 0.6

    def classify(self, change: FileChange, ctx: Any) -> List[Operation]:
        lang = change.language
        if not lang:
            return self._fallback(change, ctx)

        before = parse_source(change.body_before, lang)
        after = parse_source(change.body_after, lang)
        if before.tree is None or after.tree is None:
            return self._fallback(change, ctx)

        defs_before = _collect_definitions(before, lang)
        defs_after = _collect_definitions(after, lang)

        # Name sets
        names_before = {name for _ct, name, _n in defs_before}
        names_after = {name for _ct, name, _n in defs_after}

        removed = names_before - names_after
        added = names_after - names_before

        ops: List[Operation] = []

        # 1) Container-matched renames: same (type, order-index) across sides,
        # name swapped, bodies match modulo rename.
        by_type_before: Dict[str, List[Tuple[str, Any]]] = {}
        by_type_after: Dict[str, List[Tuple[str, Any]]] = {}
        for ct, name, n in defs_before:
            by_type_before.setdefault(ct, []).append((name, n))
        for ct, name, n in defs_after:
            by_type_after.setdefault(ct, []).append((name, n))

        claimed_before: set[int] = set()
        claimed_after: set[int] = set()

        for ct in by_type_before.keys() & by_type_after.keys():
            a = by_type_before[ct]
            b = by_type_after[ct]
            # positional pairing when counts match — common refactor shape
            if len(a) == len(b):
                for idx, ((old, nold), (new, nnew)) in enumerate(zip(a, b)):
                    if old == new:
                        continue
                    # Require rename: old ∈ removed, new ∈ added
                    if old not in removed or new not in added:
                        continue
                    body_a = _body_of(nold, before.source)
                    body_b = _body_of(nnew, after.source)
                    norm_a = _normalized_body(body_a, old, new)
                    norm_b = _normalized_body(body_b, new, new)
                    if norm_a == norm_b:
                        conf = 0.88
                        similarity = 1.0
                    else:
                        # Tolerant match: Jaccard on token sets. High overlap =
                        # same function + rename + a handful of body tweaks.
                        from difflib import SequenceMatcher
                        similarity = SequenceMatcher(None, norm_a, norm_b).ratio()
                        if similarity < 0.6:
                            continue
                        conf = 0.60 + 0.25 * (similarity - 0.6) / 0.4  # 0.60..0.85
                    call_sites = _count_identifier(change.body_after, new)
                    if ctx is not None:
                        conf = min(1.0, conf + ctx.prior_for("rename-symbol"))
                    ops.append(Operation(
                        kind=self.kind,
                        file=change.path,
                        confidence=conf,
                        summary=f"renamed `{old}` -> `{new}` ({ct})",
                        before=body_a[:300],
                        after=body_b[:300],
                        evidence={
                            "old_name": old,
                            "new_name": new,
                            "container": ct,
                            "call_sites": call_sites,
                            "body_similarity": round(similarity, 3),
                            "prior_keywords": ctx.prior_description("rename-symbol") if ctx else "",
                        },
                    ))
                    claimed_before.add(id(nold))
                    claimed_after.add(id(nnew))
                    removed.discard(old)
                    added.discard(new)

        # 2) Identifier-rename fallback: pure-identifier swap across the
        # whole file, no structural matching required. Only runs when the
        # structural pass found nothing — otherwise we'd double-report.
        if not ops:
            idents = self._detect_identifier_rename(change.body_before, change.body_after)
            for old, new, occurrences in idents:
                conf = 0.75 + min(0.15, occurrences * 0.02)
                if ctx is not None:
                    conf = min(1.0, conf + ctx.prior_for("rename-symbol"))
                ops.append(Operation(
                    kind=self.kind,
                    file=change.path,
                    confidence=conf,
                    summary=f"renamed `{old}` → `{new}` ({occurrences} references)",
                    evidence={
                        "old_name": old,
                        "new_name": new,
                        "call_sites": occurrences,
                        "detection": "identifier-swap",
                    },
                ))

        return ops

    def _fallback(self, change: FileChange, ctx: Any) -> List[Operation]:
        """Line-diff heuristic used when tree-sitter can't help."""
        ops: List[Operation] = []
        idents = self._detect_identifier_rename(change.body_before, change.body_after)
        for old, new, occurrences in idents:
            conf = 0.65 + min(0.15, occurrences * 0.02)
            if ctx is not None:
                conf = min(1.0, conf + ctx.prior_for("rename-symbol"))
            ops.append(Operation(
                kind=self.kind,
                file=change.path,
                confidence=conf,
                summary=f"renamed `{old}` → `{new}` ({occurrences} occurrences, text-level)",
                evidence={"old_name": old, "new_name": new, "call_sites": occurrences,
                          "detection": "text-fallback"},
            ))
        return ops

    @staticmethod
    def _detect_identifier_rename(before: str, after: str) -> List[Tuple[str, str, int]]:
        """Token-stable rename: if replacing `old -> new` in `before` makes
        its sorted-identifier-set equal to `after`'s, we have a rename."""
        b_idents = IDENT_RE.findall(before)
        a_idents = IDENT_RE.findall(after)
        if not b_idents or not a_idents:
            return []
        b_set = set(b_idents)
        a_set = set(a_idents)
        removed = b_set - a_set
        added = a_set - b_set
        # minimal edit distance at set level — single removed + single added
        if len(removed) != 1 or len(added) != 1:
            return []
        old = next(iter(removed))
        new = next(iter(added))
        # counts must match
        if b_idents.count(old) != a_idents.count(new):
            return []
        # verify that replacing old->new in `before` yields identifier-equiv `after`
        projected = re.sub(rf"\b{re.escape(old)}\b", new, before)
        # normalize whitespace; it's fine if formatting differs
        if re.sub(r"\s+", " ", projected).strip() == re.sub(r"\s+", " ", after).strip():
            return [(old, new, a_idents.count(new))]
        # permissive: identifier sequences match
        if IDENT_RE.findall(projected) == a_idents:
            return [(old, new, a_idents.count(new))]
        return []
