"""Per-region concurrent-operation classifier.

Two entry points:

* ``classify_region(region)`` — works from a parsed conflict region
  (ours/theirs strings, optional base). Used by the CLI inspector.
* ``classify_three_blobs(base, ours, theirs, path)`` — works from raw
  blobs (e.g. the merge driver's %O, %A, %B inputs). Returns a single
  ``ConflictRegion`` if the three are conflicting, or ``None`` if a
  trivial resolution exists.

Both heuristic. They share the same scoring helpers below.
"""
from __future__ import annotations

import difflib
import re
from typing import List, Optional, Tuple

from diffsextant.conflict.types import ConflictKind, ConflictRegion


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


# A "symbol-like" token: identifier characters, common across all our
# supported languages. We keep it ASCII to stay fast and predictable.
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokens(s: str) -> List[str]:
    return _IDENT.findall(s)


def _multiset_diff(a: List[str], b: List[str]) -> Tuple[List[str], List[str]]:
    """Return (only-in-a, only-in-b) preserving order, multiset-aware."""
    rem_b = list(b)
    only_a: List[str] = []
    for t in a:
        if t in rem_b:
            rem_b.remove(t)
        else:
            only_a.append(t)
    return only_a, rem_b


def _line_set(s: str) -> List[str]:
    return [ln.rstrip() for ln in s.splitlines() if ln.strip()]


def _ratio(a: str, b: str) -> float:
    """Quick similarity in [0,1]; tolerant of empty inputs."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# ---------------------------------------------------------------------------
# rename detection (single-symbol)
# ---------------------------------------------------------------------------


def _detect_rename_pair(
    ours: str, theirs: str, base: Optional[str]
) -> Optional[Tuple[str, str, str]]:
    """If ours/theirs differ from base only in one identifier, return
    ``(base_name, ours_name, theirs_name)``. Otherwise None.

    When ``base`` is None we can still spot a likely concurrent rename
    by comparing ours/theirs alone — both sides should be identical
    *except* for one identifier swap.
    """
    if base is not None:
        ob = _diff_one_ident(base, ours)
        tb = _diff_one_ident(base, theirs)
        if ob and tb and ob[0] == tb[0] and ob[1] != tb[1]:
            return (ob[0], ob[1], tb[1])
        return None

    # No base — compare ours/theirs structurally.
    pair = _diff_one_ident(ours, theirs)
    if not pair:
        return None
    base_guess, theirs_name = pair
    return ("?", base_guess, theirs_name)


def _diff_one_ident(a: str, b: str) -> Optional[Tuple[str, str]]:
    """If `a` -> `b` is a single-identifier substitution, return
    ``(old_ident, new_ident)``. Otherwise None.

    We tokenise both, compute the symmetric difference, and require:
      * exactly one token only-in-a
      * exactly one token only-in-b
      * the two strings, with `old` -> `new` substituted, are equal
    """
    ta, tb = _tokens(a), _tokens(b)
    only_a, only_b = _multiset_diff(ta, tb)
    if len(only_a) < 1 or len(only_b) < 1:
        return None
    # Same identifier appearing N times on each side
    if len(set(only_a)) != 1 or len(set(only_b)) != 1:
        return None
    old, new = only_a[0], only_b[0]
    if old == new:
        return None
    # Substitute and compare — must match modulo identifier
    substituted = re.sub(rf"\b{re.escape(old)}\b", new, a)
    if substituted == b:
        return (old, new)
    return None


# ---------------------------------------------------------------------------
# move detection
# ---------------------------------------------------------------------------


def _detect_move(
    ours: str, theirs: str, base: Optional[str]
) -> Optional[str]:
    """Both sides preserve the same set of *lines* but in different
    order — classic concurrent-move. Returns a one-line rationale or
    None."""
    ours_lines = _line_set(ours)
    theirs_lines = _line_set(theirs)
    if not ours_lines or not theirs_lines:
        return None
    if sorted(ours_lines) != sorted(theirs_lines):
        return None
    if ours_lines == theirs_lines:
        return None  # same content & order — not a move
    # If we have a base, ensure neither side just kept it verbatim
    if base is not None:
        base_lines = _line_set(base)
        if ours_lines == base_lines or theirs_lines == base_lines:
            return None
    return "Both sides keep the same lines but reorder them."


# ---------------------------------------------------------------------------
# region-level classifier
# ---------------------------------------------------------------------------


def classify_region(region: ConflictRegion) -> ConflictRegion:
    """Mutate `region` in place: set kind, confidence, rationale,
    intent_signals. Returns the same region (for chaining)."""
    ours = region.ours
    theirs = region.theirs
    base = region.base  # may be None

    # 1. add-add: base is empty (diff3) but both sides added content
    if base is not None and not base.strip() and (ours.strip() or theirs.strip()):
        region.kind = ConflictKind.ADD_ADD
        region.confidence = 0.9
        region.rationale = "Base is empty; both sides introduced content."
        _add_intent(region, ours, theirs)
        return region

    # 2. modify-delete: one side empty, the other not, with base content
    if base is not None and base.strip():
        if not ours.strip() and theirs.strip():
            region.kind = ConflictKind.MODIFY_DELETE
            region.confidence = 0.9
            region.rationale = "Ours deleted the block; theirs modified it."
            _add_intent(region, ours, theirs)
            return region
        if not theirs.strip() and ours.strip():
            region.kind = ConflictKind.MODIFY_DELETE
            region.confidence = 0.9
            region.rationale = "Theirs deleted the block; ours modified it."
            _add_intent(region, ours, theirs)
            return region

    # 3. concurrent-rename: single-identifier swap on each side
    rn = _detect_rename_pair(ours, theirs, base)
    if rn is not None:
        base_name, ours_name, theirs_name = rn
        region.kind = ConflictKind.CONCURRENT_RENAME
        region.confidence = 0.85 if base is not None else 0.65
        if base is not None:
            region.rationale = (
                f"Both sides renamed `{base_name}` — "
                f"ours -> `{ours_name}`, theirs -> `{theirs_name}`."
            )
        else:
            region.rationale = (
                f"Likely concurrent rename: ours uses `{ours_name}`, "
                f"theirs uses `{theirs_name}`."
            )
        region.intent_signals.append(f"ours: rename to `{ours_name}`")
        region.intent_signals.append(f"theirs: rename to `{theirs_name}`")
        return region

    # 4. concurrent-move: same line content, different order
    mv = _detect_move(ours, theirs, base)
    if mv is not None:
        region.kind = ConflictKind.CONCURRENT_MOVE
        region.confidence = 0.7
        region.rationale = mv
        region.intent_signals.append("ours and theirs preserve the same lines")
        return region

    # 5. concurrent-edit: ours/theirs both differ from base (if known)
    #    and from each other, but neither matches a sharper pattern
    if ours.strip() and theirs.strip():
        sim = _ratio(ours, theirs)
        region.kind = ConflictKind.CONCURRENT_EDIT
        # Higher similarity -> we're more confident it really is "two
        # edits to the same block" rather than independent rewrites
        region.confidence = round(0.4 + 0.4 * sim, 3)
        region.rationale = (
            f"Both sides edited overlapping content (similarity "
            f"{sim:.2f})."
        )
        _add_intent(region, ours, theirs)
        return region

    # Fallback
    region.kind = ConflictKind.UNKNOWN
    region.confidence = 0.0
    region.rationale = "Could not classify — leaving for human review."
    return region


def _add_intent(region: ConflictRegion, ours: str, theirs: str) -> None:
    o_tok = set(_tokens(ours))
    t_tok = set(_tokens(theirs))
    only_o = sorted(o_tok - t_tok)
    only_t = sorted(t_tok - o_tok)
    if only_o:
        region.intent_signals.append(
            "ours-only tokens: " + ", ".join(only_o[:6])
        )
    if only_t:
        region.intent_signals.append(
            "theirs-only tokens: " + ", ".join(only_t[:6])
        )


# ---------------------------------------------------------------------------
# three-blob entry — used by the merge driver
# ---------------------------------------------------------------------------


def classify_three_blobs(
    base: str, ours: str, theirs: str, path: str = "<blob>"
) -> Optional[ConflictRegion]:
    """Build a synthetic single-region from three blobs and classify it.

    Returns:
        * a classified region if the three blobs disagree
        * None if a trivial 3-way resolution exists (one side == base)
    """
    if ours == theirs:
        return None
    if ours == base:
        # Theirs is the only change — git would auto-take it
        return None
    if theirs == base:
        # Ours is the only change
        return None
    region = ConflictRegion(
        index=1,
        line_start=1,
        line_end=max(1, ours.count("\n") + 1),
        ours_label="ours",
        theirs_label="theirs",
        base_label="base",
        ours=ours,
        theirs=theirs,
        base=base,
    )
    return classify_region(region)
