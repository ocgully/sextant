"""Risk assessment (§9) — standalone-first (§4.6).

Risk signals:
- public_api_impact  — symbol exported? (tree-sitter heuristic when
                       Mercator absent)
- call_site_count    — grep-like count in the worktree
- test_coverage_delta — did any test file change in the same diff?
- blame_churn        — frequency of historical churn on touched region
- cross_module_reach — number of distinct top-level dirs touched
- file_size_delta    — simple bytes delta

Mercator + Pedia bridges may fill the first three more richly; in 1A we
default to AST + path-based heuristics.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from sextant.git_context import GitContext, blame_churn
from sextant.ops.base import Operation, OperationKind
from sextant.parse import parse_source, find_nodes, node_text


BUCKETS = ["low", "medium", "high", "critical"]


# ---------------------------------------------------------------------------
# public-API heuristics
# ---------------------------------------------------------------------------


def is_public_symbol(body_after: str, language: Optional[str], symbol: str) -> bool:
    """Tree-sitter-less AST heuristic per language."""
    if not body_after or not symbol:
        return False
    if language == "python":
        # Exported if in __all__ OR doesn't start with underscore (public by convention)
        m = re.search(r"__all__\s*=\s*\[([^\]]+)\]", body_after)
        if m and re.search(rf"['\"]{re.escape(symbol)}['\"]", m.group(1)):
            return True
        return not symbol.startswith("_")
    if language in ("typescript", "tsx", "javascript"):
        return bool(re.search(rf"\bexport\b[^;]*\b{re.escape(symbol)}\b", body_after))
    if language == "rust":
        return bool(re.search(rf"\bpub\b[^;]*\b{re.escape(symbol)}\b", body_after))
    if language == "go":
        # Go: capitalized identifier is exported
        return bool(symbol) and symbol[0].isupper()
    return False


# ---------------------------------------------------------------------------
# call-site counting (AST-validated grep)
# ---------------------------------------------------------------------------


def count_call_sites(cwd: Path, symbol: str, exclude_path: Optional[str] = None) -> int:
    if not symbol:
        return 0
    try:
        r = subprocess.run(
            ["git", "grep", "-n", "-w", symbol],
            cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        return 0
    if r.returncode not in (0, 1):
        return 0
    count = 0
    for line in r.stdout.splitlines():
        # line format: path:lineno:text
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        if exclude_path and parts[0] == exclude_path:
            continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------


def bucket_score(score: float) -> str:
    if score >= 0.85:
        return "critical"
    if score >= 0.60:
        return "high"
    if score >= 0.30:
        return "medium"
    return "low"


def assess(op: Operation, *, cwd: Path, git_ctx: Optional[GitContext],
           all_changes, mode: str = "basic") -> Dict[str, Any]:
    """Produce a signal dict + an aggregate bucket for `op`.
    `mode`: off | basic | full. Full attempts Mercator + Pedia bridges.
    """
    if mode == "off":
        return {"bucket": "low", "signals": {}}

    signals: Dict[str, Any] = {}
    score = 0.0

    # -- public-API heuristic --
    ev = op.evidence or {}
    symbol = ev.get("new_name") or ev.get("symbol") or ev.get("function") or ""
    if symbol:
        is_public = is_public_symbol("", None, symbol)
        # Best-effort: actually inspect the after-body from the relevant change
        for ch in all_changes:
            if ch.path == op.file and ch.body_after:
                is_public = is_public_symbol(ch.body_after, ch.language, symbol)
                break
        signals["public_api_impact"] = bool(is_public)
        if is_public:
            score += 0.35

    # -- call-site count --
    if symbol:
        try:
            sites = count_call_sites(cwd, symbol, exclude_path=op.file)
            signals["call_site_count"] = sites
            if sites > 20:
                score += 0.30
            elif sites > 5:
                score += 0.15
            elif sites > 0:
                score += 0.05
        except Exception:
            pass

    # -- test coverage delta --
    test_touched = False
    for ch in all_changes:
        path = ch.path_after or ch.path_before or ""
        if re.search(r"(^|/)tests?/|test_|_test\.|\.test\.|_spec\.", path):
            if ch.body_before != ch.body_after:
                test_touched = True
                break
    signals["test_coverage_delta"] = test_touched
    if test_touched:
        score -= 0.10  # lowers risk
    else:
        if op.kind in (OperationKind.CHANGE_SIGNATURE, OperationKind.RENAME_SYMBOL,
                       OperationKind.EXTRACT_FUNCTION):
            score += 0.10  # raises risk when no test coverage

    # -- blame churn --
    if git_ctx and git_ctx.is_repo:
        churn = blame_churn(cwd, op.file, 1, 200) if op.file else None
        if churn is not None:
            signals["blame_churn"] = churn
            # High churn = risk LOWER (routine change territory)
            if churn >= 10:
                score -= 0.05

    # -- cross-module reach --
    top_dirs = set()
    for ch in all_changes:
        p = ch.path_after or ch.path_before or ""
        parts = p.split("/")
        if len(parts) > 1:
            top_dirs.add(parts[0])
    signals["cross_module_reach"] = len(top_dirs)
    if len(top_dirs) > 4:
        score += 0.20
    elif len(top_dirs) > 2:
        score += 0.10

    # -- file size delta --
    for ch in all_changes:
        if ch.path == op.file:
            delta = len(ch.body_after or "") - len(ch.body_before or "")
            signals["file_size_delta_bytes"] = delta
            if abs(delta) > 5000:
                score += 0.15
            break

    # Operation-intrinsic risk (some kinds are higher-risk by nature)
    if op.kind == OperationKind.MALFORMED:
        score = 1.0
    if op.kind in (OperationKind.GOD_CLASS_FORMING, OperationKind.SHOTGUN_SURGERY):
        score += 0.20

    # Commit-message bias
    if git_ctx and git_ctx.bias_flags.get("risk_up"):
        score += 0.10

    score = max(0.0, min(1.0, score))
    return {
        "bucket": bucket_score(score),
        "score": round(score, 3),
        "signals": signals,
    }


def enrich(result, *, cwd: Path, mode: str = "basic") -> None:
    """Mutate ops in-place, attaching `op.risk` dicts."""
    if mode == "off":
        return
    for op in result.operations:
        op.risk = assess(op, cwd=cwd, git_ctx=result.git_context,
                         all_changes=result.changes, mode=mode)
