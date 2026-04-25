"""Fixture-based tests for the conflict module (phase 1D).

Each directory under ``tests/fixtures/conflicts/<kind>/`` carries:
  * ``base.txt``    — common ancestor blob (may be empty)
  * ``ours.txt``    — our side
  * ``theirs.txt``  — their side
  * ``expected.json`` — assertions to run

We deliberately use a *predicate* shape for ``expected.json`` — minimum
confidence, expected suggestion keys, intent-signal substrings — rather
than a verbatim snapshot, because the exact wording of rationales is
heuristic and we don't want to lock the prose in.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from diffsextant.conflict import (
    analyze_three_blobs,
    parse_conflict_text,
    classify_region,
    suggest_for_region,
)
from diffsextant.conflict.types import ConflictKind


CONFLICTS_ROOT = Path(__file__).parent / "fixtures" / "conflicts"


def _iter_conflict_fixtures():
    if not CONFLICTS_ROOT.exists():
        return
    for sub in sorted(CONFLICTS_ROOT.iterdir()):
        if not sub.is_dir():
            continue
        if not (sub / "expected.json").exists():
            continue
        yield sub


# ---------------------------------------------------------------------------
# parametrised fixture run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture_dir",
    list(_iter_conflict_fixtures()),
    ids=lambda p: p.name,
)
def test_three_blob_classification(fixture_dir: Path) -> None:
    base = (fixture_dir / "base.txt").read_text(encoding="utf-8")
    ours = (fixture_dir / "ours.txt").read_text(encoding="utf-8")
    theirs = (fixture_dir / "theirs.txt").read_text(encoding="utf-8")
    expected: Dict[str, Any] = json.loads(
        (fixture_dir / "expected.json").read_text(encoding="utf-8")
    )

    region = analyze_three_blobs(base, ours, theirs, path=fixture_dir.name)
    assert region is not None, (
        f"{fixture_dir.name}: expected a classified region, got None "
        f"(would mean the three blobs trivially merge)"
    )

    # 1. kind matches
    assert region.kind.value == expected["kind"], (
        f"{fixture_dir.name}: kind={region.kind.value} "
        f"expected={expected['kind']}\nrationale: {region.rationale}"
    )

    # 2. confidence floor
    assert region.confidence >= float(expected["min_confidence"]), (
        f"{fixture_dir.name}: confidence {region.confidence} "
        f"< {expected['min_confidence']}"
    )

    # 3. risk bucket matches
    assert region.risk_bucket() == expected["risk_bucket"], (
        f"{fixture_dir.name}: risk_bucket={region.risk_bucket()} "
        f"expected={expected['risk_bucket']}"
    )

    # 4. expected suggestion keys are *all* present
    got_keys = [s.key for s in region.suggestions]
    for k in expected["suggestion_keys"]:
        assert k in got_keys, (
            f"{fixture_dir.name}: missing suggestion key `{k}`; "
            f"got {got_keys}"
        )

    # 5. intent-signal substring assertions (optional)
    for needle in expected.get("expected_intent_signals_substrings", []):
        joined = " | ".join(region.intent_signals)
        assert needle in joined, (
            f"{fixture_dir.name}: intent signals do not mention `{needle}`; "
            f"got: {region.intent_signals}"
        )


# ---------------------------------------------------------------------------
# unit tests for the parser (independent of fixtures)
# ---------------------------------------------------------------------------


def test_parser_simple_two_way():
    text = (
        "before\n"
        "<<<<<<< HEAD\n"
        "ours line 1\n"
        "ours line 2\n"
        "=======\n"
        "theirs line 1\n"
        ">>>>>>> feat/x\n"
        "after\n"
    )
    cf = parse_conflict_text(text, path="t.py")
    assert cf.parse_ok is True
    assert len(cf.regions) == 1
    r = cf.regions[0]
    assert r.ours_label == "HEAD"
    assert r.theirs_label == "feat/x"
    assert r.ours == "ours line 1\nours line 2"
    assert r.theirs == "theirs line 1"
    assert r.base is None  # no diff3 markers
    assert r.line_start == 2
    assert r.line_end == 7


def test_parser_diff3_format_carries_base():
    text = (
        "<<<<<<< HEAD\n"
        "ours\n"
        "||||||| merged common ancestors\n"
        "common\n"
        "=======\n"
        "theirs\n"
        ">>>>>>> branch\n"
    )
    cf = parse_conflict_text(text)
    assert cf.parse_ok
    r = cf.regions[0]
    assert r.base == "common"
    assert r.base_label == "merged common ancestors"


def test_parser_unterminated_block_marks_parse_error():
    text = (
        "<<<<<<< HEAD\n"
        "ours\n"
        "=======\n"
        "theirs\n"
        # no >>>>>>>
    )
    cf = parse_conflict_text(text)
    assert cf.parse_ok is False
    assert "unterminated" in cf.parse_error
    assert len(cf.regions) == 1


def test_parser_no_conflict_returns_empty_regions():
    cf = parse_conflict_text("just some code\nno conflict here\n")
    assert cf.parse_ok is True
    assert cf.regions == []


def test_parser_multiple_regions():
    text = (
        "<<<<<<< HEAD\n"
        "a\n"
        "=======\n"
        "A\n"
        ">>>>>>> br\n"
        "middle\n"
        "<<<<<<< HEAD\n"
        "b\n"
        "=======\n"
        "B\n"
        ">>>>>>> br\n"
    )
    cf = parse_conflict_text(text)
    assert cf.parse_ok
    assert len(cf.regions) == 2
    assert cf.regions[0].ours == "a"
    assert cf.regions[1].theirs == "B"


# ---------------------------------------------------------------------------
# classifier — trivial-resolution short-circuit
# ---------------------------------------------------------------------------


def test_classifier_returns_none_when_ours_equals_base():
    region = analyze_three_blobs("same\n", "same\n", "different\n")
    assert region is None  # git could take theirs cleanly


def test_classifier_returns_none_when_theirs_equals_base():
    region = analyze_three_blobs("same\n", "different\n", "same\n")
    assert region is None


def test_classifier_returns_none_when_ours_equals_theirs():
    region = analyze_three_blobs("base\n", "same\n", "same\n")
    assert region is None


# ---------------------------------------------------------------------------
# rename detector — both sides agree on the new name (rare but possible)
# ---------------------------------------------------------------------------


def test_rename_both_sides_same_target():
    """Both sides independently performed the *same* rename — sextant
    should be able to pick it cleanly via the merge driver path."""
    region = analyze_three_blobs(
        "x = old_name + 1\n",
        "x = new_name + 1\n",
        "x = new_name + 1\n",
    )
    # ours == theirs => trivial resolve, no region needed
    assert region is None


# ---------------------------------------------------------------------------
# add-add via parsed marker form (no diff3) — should still classify but
# without the strong "base is empty" signal
# ---------------------------------------------------------------------------


def test_concurrent_edit_via_parser():
    text = (
        "<<<<<<< HEAD\n"
        "config.timeout = 30\n"
        "=======\n"
        "config.retries = 5\n"
        ">>>>>>> feat\n"
    )
    cf = parse_conflict_text(text)
    assert cf.regions
    region = cf.regions[0]
    classify_region(region)
    suggest_for_region(region)
    # Without base, the parser path should still surface a non-UNKNOWN kind
    assert region.kind != ConflictKind.UNKNOWN
    assert region.suggestions, "expected at least one suggestion"
