"""Text renderer — ANSI-colored terminal output.

Layout per diff:
  ── operations ──
    [kind] summary                   (conf: ##%  risk: ##)
  ── narrative ──     (git-context footer, §4.7)
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional

from sextant.ops.base import Operation, OperationKind


# ---------------------------------------------------------------------------
# ANSI — gated on stdout-isatty + NO_COLOR env
# ---------------------------------------------------------------------------


def _ansi_enabled(stream=sys.stdout) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return getattr(stream, "isatty", lambda: False)()


def _color(text: str, code: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


# Kind -> ANSI palette entry
KIND_COLORS = {
    OperationKind.RENAME_SYMBOL: "36",        # cyan
    OperationKind.EXTRACT_FUNCTION: "35",     # magenta
    OperationKind.MOVE_FILE: "34",            # blue
    OperationKind.MOVE_SYMBOL: "34",
    OperationKind.REFORMAT: "33",             # yellow
    OperationKind.LINT_FIX: "33",
    OperationKind.COMMENT_ONLY: "90",         # bright black
    OperationKind.DOCSTRING_ONLY: "90",
    OperationKind.ADD_IMPORT: "32",           # green
    OperationKind.REMOVE_IMPORT: "31",        # red
    OperationKind.REORDER_IMPORTS: "33",
    OperationKind.REORDER_STATEMENTS: "33",
    OperationKind.INVERT_CONDITION: "35",
    OperationKind.CHANGE_SIGNATURE: "35",
    OperationKind.ADD_TEST: "32",
    OperationKind.REMOVE_TEST: "31",
    OperationKind.RENAME_TEST: "36",
    OperationKind.STRATEGY_PATTERN_INTRO: "95",   # bright magenta
    OperationKind.GOD_CLASS_FORMING: "31;1",       # bold red
    OperationKind.SHOTGUN_SURGERY: "31;1",
    OperationKind.MALFORMED: "41;97",              # white on red
    OperationKind.PLAIN_EDIT: "37",                # white
}

RISK_COLORS = {
    "critical": "41;97",
    "high": "31;1",
    "medium": "33",
    "low": "32",
}


def render_text(result, *, threshold: float = 0.0, show_evidence: bool = False) -> str:
    """Pretty-print a DiffResult. ANSI automatically enabled for TTY."""
    color = _ansi_enabled()
    lines: List[str] = []

    # Header
    ctx = result.git_context
    if ctx and ctx.is_repo:
        header = f"sextant: {ctx.branch or '?'}"
        if ctx.upstream:
            header += f" ← {ctx.upstream}"
        if ctx.commit_range:
            header += f"  ({ctx.commit_range[0]}..{ctx.commit_range[1]})"
        if ctx.pick_state:
            header += f"  [{ctx.pick_state}]"
        lines.append(_color(header, "1", color))
        lines.append("")

    # Operations
    malformed = [op for op in result.operations if op.kind == OperationKind.MALFORMED]
    if malformed:
        lines.append(_color("── MALFORMED files ──", "41;97", color))
        for op in malformed:
            lines.extend(_fmt_op(op, color, show_evidence, is_malformed=True))
        lines.append("")

    other = [op for op in result.operations
             if op.kind != OperationKind.MALFORMED and op.confidence >= threshold]
    if other:
        lines.append(_color("── operations ──", "1", color))
        for op in other:
            lines.extend(_fmt_op(op, color, show_evidence))
        lines.append("")

    if not result.operations:
        lines.append("  (no operations classified — no files changed?)")
        lines.append("")

    # Narrative footer
    if ctx and ctx.is_repo and ctx.commit_messages:
        lines.append(_color("── narrative ──", "1", color))
        for m in ctx.commit_messages[:3]:
            sha = (m.get("sha") or "")[:8]
            subj = m.get("subject") or ""
            lines.append(f"  {sha}  {subj}")
        if ctx.adjacent_before:
            lines.append(
                f"  before:  {(ctx.adjacent_before.get('sha') or '')[:8]}  "
                f"{ctx.adjacent_before.get('subject') or ''}"
            )
        if ctx.adjacent_after:
            lines.append(
                f"  after:   {(ctx.adjacent_after.get('sha') or '')[:8]}  "
                f"{ctx.adjacent_after.get('subject') or ''}"
            )
        # Active priors
        active = []
        for kind_str in ("rename-symbol", "extract-function", "move-file",
                         "reformat", "lint-fix", "invert-condition", "change-signature"):
            prior = ctx.prior_for(kind_str)
            if prior > 0:
                active.append(f"{kind_str} (+{prior:.2f})")
        if active:
            lines.append("  commit-msg priors active: " + ", ".join(active))
        lines.append("")

    if result.warnings:
        lines.append(_color("── warnings ──", "33", color))
        for w in result.warnings:
            lines.append(f"  {w}")
        lines.append("")

    return "\n".join(lines)


def _fmt_op(op: Operation, color: bool, show_evidence: bool,
            is_malformed: bool = False) -> List[str]:
    kind_color = KIND_COLORS.get(op.kind, "37")
    kind_label = _color(f"[{op.kind.value}]", kind_color, color)
    risk_part = ""
    if op.risk:
        rc = RISK_COLORS.get(op.risk.get("bucket", "low"), "37")
        risk_part = _color(f"  risk:{op.risk['bucket']}", rc, color)
    conf_pct = int(round(op.confidence * 100))
    conf_part = _color(f"conf:{conf_pct}%", "90", color)
    out = [f"  {kind_label} {op.summary}   ({conf_part}{risk_part})"]
    if op.file:
        out.append(f"      file: {op.file}")
    if op.related_files:
        if len(op.related_files) == 1:
            out.append(f"      related: {op.related_files[0]}")
        else:
            out.append(f"      related: {len(op.related_files)} files")
    if show_evidence and op.evidence:
        for k, v in list(op.evidence.items())[:6]:
            out.append(f"        {k}: {v}")
    return out
