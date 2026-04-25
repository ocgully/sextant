"""Risk-aware resolution suggestions per region.

Each ``ConflictKind`` has a tailored suggestion list. Suggestions never
exfiltrate creative resolutions; they offer one of:

  * keep both sides side-by-side (when meaningfully composable)
  * unify to one side
  * abort to base
  * manual edit

Auto-applicable suggestions set ``Suggestion.body`` to the replacement
text the merge driver / ``--resolve`` mode would write.
"""
from __future__ import annotations

import re
from typing import List, Optional

from sextant.conflict.types import ConflictKind, ConflictRegion, Suggestion
from sextant.conflict.classifier import _diff_one_ident, _tokens


def suggest_for_region(region: ConflictRegion) -> List[Suggestion]:
    """Produce a list of suggestions, store on ``region.suggestions``,
    and return it."""
    sugs: List[Suggestion] = []

    if region.kind == ConflictKind.CONCURRENT_RENAME:
        sugs.extend(_suggest_concurrent_rename(region))
    elif region.kind == ConflictKind.CONCURRENT_MOVE:
        sugs.extend(_suggest_concurrent_move(region))
    elif region.kind == ConflictKind.CONCURRENT_EDIT:
        sugs.extend(_suggest_concurrent_edit(region))
    elif region.kind == ConflictKind.ADD_ADD:
        sugs.extend(_suggest_add_add(region))
    elif region.kind == ConflictKind.MODIFY_DELETE:
        sugs.extend(_suggest_modify_delete(region))
    else:
        sugs.append(Suggestion(
            key="m", label="Manual edit",
            detail="Sextant could not classify; review the region manually.",
        ))
        if region.base is not None:
            sugs.append(Suggestion(
                key="a", label="Abort to base",
                detail="Restore base content; discard both sides.",
                body=region.base, auto_apply=True,
            ))

    region.suggestions = sugs
    return sugs


# ---------------------------------------------------------------------------
# per-kind builders
# ---------------------------------------------------------------------------


def _suggest_concurrent_rename(region: ConflictRegion) -> List[Suggestion]:
    sugs: List[Suggestion] = []
    base_name, ours_name, theirs_name = _extract_rename_names(region)

    sugs.append(Suggestion(
        key="k", label="Keep both — split usage",
        detail=(
            f"Use `{ours_name}` in ours-side files and `{theirs_name}` "
            f"in theirs-side files. Manual follow-up required across the repo."
        ),
    ))

    if ours_name:
        sugs.append(Suggestion(
            key="u", label=f"Unify to `{ours_name}`",
            detail=f"Adopt the ours-side rename ({ours_name}) everywhere.",
            body=region.ours, auto_apply=True,
        ))
    if theirs_name:
        sugs.append(Suggestion(
            key="u-other", label=f"Unify to `{theirs_name}`",
            detail=f"Adopt the theirs-side rename ({theirs_name}) everywhere.",
            body=region.theirs, auto_apply=True,
        ))
    if region.base is not None and base_name and base_name != "?":
        sugs.append(Suggestion(
            key="a", label=f"Abort to base (`{base_name}`)",
            detail="Discard both renames; restore the original symbol.",
            body=region.base, auto_apply=True,
        ))

    sugs.append(Suggestion(
        key="m", label="Manual edit",
        detail="Open the region in your editor.",
    ))
    return sugs


def _extract_rename_names(region: ConflictRegion) -> tuple[str, str, str]:
    base = region.base or ""
    pair_o = _diff_one_ident(base, region.ours) if region.base is not None else None
    pair_t = _diff_one_ident(base, region.theirs) if region.base is not None else None
    if pair_o and pair_t:
        return (pair_o[0], pair_o[1], pair_t[1])
    pair_ot = _diff_one_ident(region.ours, region.theirs)
    if pair_ot:
        return ("?", pair_ot[0], pair_ot[1])
    return ("?", "", "")


def _suggest_concurrent_move(region: ConflictRegion) -> List[Suggestion]:
    return [
        Suggestion(
            key="u", label="Take ours ordering",
            detail="Both sides have the same content; pick ours' order.",
            body=region.ours, auto_apply=True,
        ),
        Suggestion(
            key="u-other", label="Take theirs ordering",
            detail="Both sides have the same content; pick theirs' order.",
            body=region.theirs, auto_apply=True,
        ),
        Suggestion(
            key="m", label="Manual edit",
            detail="Decide an explicit ordering yourself.",
        ),
    ]


def _suggest_concurrent_edit(region: ConflictRegion) -> List[Suggestion]:
    sugs = [
        Suggestion(
            key="u", label="Take ours",
            body=region.ours, auto_apply=True,
        ),
        Suggestion(
            key="u-other", label="Take theirs",
            body=region.theirs, auto_apply=True,
        ),
        Suggestion(
            key="k", label="Keep both (concatenate)",
            detail="Append theirs after ours; review for duplicates.",
            body=region.ours + "\n" + region.theirs, auto_apply=True,
        ),
    ]
    if region.base is not None:
        sugs.append(Suggestion(
            key="a", label="Abort to base",
            body=region.base, auto_apply=True,
        ))
    sugs.append(Suggestion(key="m", label="Manual edit"))
    return sugs


def _suggest_add_add(region: ConflictRegion) -> List[Suggestion]:
    return [
        Suggestion(
            key="k", label="Keep both additions",
            detail="Concatenate ours then theirs; review for duplicates.",
            body=region.ours + "\n" + region.theirs, auto_apply=True,
        ),
        Suggestion(
            key="u", label="Take ours only",
            body=region.ours, auto_apply=True,
        ),
        Suggestion(
            key="u-other", label="Take theirs only",
            body=region.theirs, auto_apply=True,
        ),
        Suggestion(key="m", label="Manual edit"),
    ]


def _suggest_modify_delete(region: ConflictRegion) -> List[Suggestion]:
    deleted_side = "ours" if not region.ours.strip() else "theirs"
    kept_body = region.theirs if deleted_side == "ours" else region.ours
    return [
        Suggestion(
            key="u", label=f"Keep the modification ({'theirs' if deleted_side == 'ours' else 'ours'})",
            detail=(
                "Modify-delete is high-risk: the deleting side may have "
                "intentionally retired the block. Verify before applying."
            ),
            body=kept_body, auto_apply=True,
        ),
        Suggestion(
            key="d", label=f"Honour the deletion ({deleted_side})",
            body="", auto_apply=True,
        ),
        Suggestion(key="m", label="Manual edit (recommended)"),
    ]
