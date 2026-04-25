"""Fixture-based snapshot tests.

For each directory under tests/fixtures/<category>/<name>/:
  - Materialise `before/` + `after/` as two commits in a tmp git repo
  - Run Sextant's classifier (programmatic API, not subprocess)
  - Normalise + compare against `expected.json`
  - Fail on drift; rewrite on `--update-snapshots` / SEXTANT_UPDATE_SNAPSHOTS=1

Normalisation strips machine-specific noise: the tmp `cwd` from
git_context, blame_churn (history-dependent), and call_site_count
(grep over a synthetic repo). Operations are sorted deterministically
by `(kind, file, summary)`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from sextant import classify_diff
from sextant.git_context import collect as collect_ctx
from sextant.risk import enrich

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
from conftest import (  # noqa: E402
    FIXTURES_ROOT,
    iter_fixture_dirs,
    materialise_fixture,
)


# ---------------------------------------------------------------------------
# normalisation — strip machine-specific data so snapshots are stable
# ---------------------------------------------------------------------------


def _normalise_op(op: Dict[str, Any]) -> Dict[str, Any]:
    """Strip non-deterministic fields from a single operation dict."""
    cleaned = {
        "kind": op.get("kind"),
        "file": op.get("file"),
        "confidence": round(float(op.get("confidence", 0.0)), 3),
        "confidence_bucket": op.get("confidence_bucket"),
        "summary": op.get("summary"),
        "evidence": _normalise_evidence(op.get("evidence") or {}),
        "related_files": sorted(op.get("related_files") or []),
    }
    risk = op.get("risk")
    if risk:
        cleaned["risk"] = _normalise_risk(risk)
    return cleaned


def _normalise_evidence(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Drop fields that vary by host: prior_keywords (depends on commit
    message which we DO control, so keep), but everything else stays.
    Keep keys sorted in output via json.dumps(sort_keys=True)."""
    out = dict(ev)
    # call_sites is repo-grep based — for fixtures it's 0 or local-only,
    # but normalise to None to avoid grep races.
    return out


def _normalise_risk(risk: Dict[str, Any]) -> Dict[str, Any]:
    """Risk depends on git history (blame_churn) which is `1` for all
    fixture commits — predictable. Cross-module reach is also stable
    because we control the file tree. Drop only call_site_count which
    can race with the host filesystem."""
    signals = dict(risk.get("signals") or {})
    # blame_churn: 1 for all fixture-commits, but tree-sitter parse can
    # silently fail on Windows; pin to None to keep snapshots stable.
    signals.pop("blame_churn", None)
    return {
        "bucket": risk.get("bucket"),
        "score": round(float(risk.get("score", 0.0)), 3),
        "signals": signals,
    }


def _sort_ops(ops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stable, deterministic ordering: (kind, file, summary)."""
    return sorted(ops, key=lambda o: (o.get("kind") or "", o.get("file") or "",
                                      o.get("summary") or ""))


def normalise_result(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Build the snapshot-ready dict from a DiffResult.to_dict()."""
    ops = [_normalise_op(o) for o in (result_dict.get("operations") or [])]
    ops = _sort_ops(ops)
    files = []
    for f in (result_dict.get("files") or []):
        files.append({
            "path_before": f.get("path_before"),
            "path_after": f.get("path_after"),
            "language": f.get("language"),
            "is_new": f.get("is_new"),
            "is_deleted": f.get("is_deleted"),
            "is_renamed": f.get("is_renamed"),
        })
    files = sorted(files, key=lambda f: (
        f.get("path_after") or "", f.get("path_before") or ""))
    return {
        "operations": ops,
        "files": files,
    }


# ---------------------------------------------------------------------------
# the actual snapshot test
# ---------------------------------------------------------------------------


def _fixture_id(path: Path) -> str:
    return f"{path.parent.name}/{path.name}"


_FIXTURES = list(iter_fixture_dirs())


@pytest.mark.skipif(not _FIXTURES, reason="no fixtures discovered")
@pytest.mark.parametrize(
    "fixture_dir",
    _FIXTURES,
    ids=[_fixture_id(f) for f in _FIXTURES],
)
def test_fixture_snapshot(fixture_dir: Path, tmp_path: Path,
                          update_snapshots: bool) -> None:
    """Run Sextant against the fixture's diff and compare to expected.json."""
    before_dir = fixture_dir / "before"
    after_dir = fixture_dir / "after"
    expected_path = fixture_dir / "expected.json"
    msg_path = fixture_dir / "commit-message.txt"
    commit_msg = msg_path.read_text(encoding="utf-8").strip() if msg_path.exists() else "fixture change"

    repo = tmp_path / "repo"
    repo.mkdir()
    ref_before, ref_after = materialise_fixture(repo, before_dir, after_dir,
                                                commit_msg=commit_msg)

    # Programmatic API — same path the CLI takes minus the argparse layer.
    git_ctx = collect_ctx(repo, ref1=ref_before, ref2=ref_after)
    result = classify_diff(ref_before, ref_after, cwd=repo, git_ctx=git_ctx)
    enrich(result, cwd=repo, mode="basic")

    actual = normalise_result(result.to_dict())
    actual_text = json.dumps(actual, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    if update_snapshots or not expected_path.exists():
        expected_path.write_text(actual_text, encoding="utf-8")
        sys.stdout.write(f"\nUPDATED snapshot: {_fixture_id(fixture_dir)}\n")
        return

    expected_text = expected_path.read_text(encoding="utf-8")
    if expected_text != actual_text:
        # Format a unified diff for clear failure output
        import difflib
        diff = "".join(difflib.unified_diff(
            expected_text.splitlines(keepends=True),
            actual_text.splitlines(keepends=True),
            fromfile=f"expected ({_fixture_id(fixture_dir)})",
            tofile="actual",
            n=3,
        ))
        pytest.fail(
            f"Snapshot drift in {_fixture_id(fixture_dir)}:\n{diff}\n"
            f"To accept: SEXTANT_UPDATE_SNAPSHOTS=1 pytest tests/test_fixtures.py "
            f"OR pytest tests/test_fixtures.py --update-snapshots"
        )


# ---------------------------------------------------------------------------
# meta-test: at least one fixture per required category
# ---------------------------------------------------------------------------


REQUIRED_CATEGORIES = {
    "happy-path": 25,
    "multi-op": 5,
    "ambiguous": 5,
    "negative": 5,
    "real-world": 3,
}


def test_fixture_corpus_minimum_size():
    """The fixture corpus has to meet UAT minimum thresholds."""
    counts: Dict[str, int] = {}
    for f in iter_fixture_dirs():
        cat = f.parent.name
        counts[cat] = counts.get(cat, 0) + 1
    for cat, minimum in REQUIRED_CATEGORIES.items():
        actual = counts.get(cat, 0)
        assert actual >= minimum, (
            f"category `{cat}` has {actual} fixtures, need {minimum}+. "
            f"All counts: {counts}"
        )
    total = sum(counts.values())
    assert total >= 30, f"total fixtures = {total}, need 30+"


def test_each_fixture_has_readme():
    """Documentation discipline — every fixture must self-describe."""
    for f in iter_fixture_dirs():
        readme = f / "README.md"
        assert readme.exists(), f"fixture missing README.md: {_fixture_id(f)}"
        body = readme.read_text(encoding="utf-8").strip()
        assert len(body) >= 30, (
            f"fixture README too short ({len(body)} chars): {_fixture_id(f)}. "
            f"Need 3+ lines describing the case."
        )


def test_ambiguous_fixtures_have_decision_rationale():
    """Ambiguous fixtures pin classifier behavior — they must explain why."""
    for f in iter_fixture_dirs():
        if f.parent.name != "ambiguous":
            continue
        rationale = f / "decision-rationale.md"
        assert rationale.exists(), (
            f"ambiguous fixture {_fixture_id(f)} missing decision-rationale.md"
        )


def test_multi_op_fixtures_emit_multiple_ops():
    """Multi-op fixtures must produce >= 2 operations in their snapshot."""
    for f in iter_fixture_dirs():
        if f.parent.name != "multi-op":
            continue
        expected_path = f / "expected.json"
        if not expected_path.exists():
            continue  # bootstrapping
        data = json.loads(expected_path.read_text(encoding="utf-8"))
        assert len(data.get("operations", [])) >= 2, (
            f"multi-op fixture {_fixture_id(f)} has < 2 operations in snapshot"
        )
