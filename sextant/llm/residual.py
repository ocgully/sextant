"""Residual classification — refine LOW-confidence ops via the agent runner.

Sextant's deterministic classifiers emit operations with a confidence
score in [0,1]. The bucket thresholds (per `ops/base.py`) are:

    > 0.9   high
    >= 0.7  medium
    < 0.7   low   ← residual zone

When `--llm` is passed to `sextant diff`, every op below the LOW
threshold is tagged ``pending_llm = True``. If a runner is detected
and not in dry-run, we build a focused prompt per residual op and
hand it to `invoke_runner`. The agent's structured response is
folded back into the op as a refinement (``llm_refinement``); the
original kind/confidence are preserved so the determinism guarantee
still holds for the rule-based core.

**The LLM never overrides high/medium classifications.** It only
refines residuals.

## Cache key

    sha256(
        op.kind + "|" +
        op.file + "|" +
        op.confidence (rounded to 3dp) + "|" +
        normalised_diff(op.before, op.after) + "|" +
        normalised_evidence(op.evidence)
    )

Cached at ``.sextant/cache/llm/<sha>.json``. Invalidates whenever the
underlying op changes shape. Independent of the diff range itself —
two unrelated diffs that produce the same residual op key share a
cache hit.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


# The classifier bucket boundary for "low-confidence". Mirrors
# `ops.base.bucket_confidence`. Centralised here so the LLM module owns
# the residual semantics in one place.
LOW_CONFIDENCE_THRESHOLD: float = 0.7


def residual_threshold() -> float:
    """Public accessor — what counts as residual?"""
    return LOW_CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# tagging
# ---------------------------------------------------------------------------


def residual_route(operations) -> List[Any]:
    """Tag every below-threshold op with ``pending_llm = True`` on its
    evidence dict, and return the subset that's now pending.

    Mutates `operations` in place — `op.evidence['pending_llm']` is
    True for residuals, False for confident ops. The deterministic
    pipeline owns ``op.kind`` / ``op.confidence``; this only adds the
    routing flag.
    """
    pending = []
    for op in operations:
        is_residual = op.confidence < LOW_CONFIDENCE_THRESHOLD
        op.evidence["pending_llm"] = bool(is_residual)
        if is_residual:
            pending.append(op)
    return pending


# ---------------------------------------------------------------------------
# cache key
# ---------------------------------------------------------------------------


def _norm(text: Optional[str]) -> str:
    """Collapse trailing whitespace + final newline so cache key is
    stable across `\\n` / `\\r\\n` and trailing-newline drift."""
    if not text:
        return ""
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(lines).rstrip("\n")


def _norm_evidence(evidence: Dict[str, Any]) -> str:
    """Stable JSON for the evidence dict, sans the routing flag itself."""
    if not evidence:
        return "{}"
    pruned = {k: v for k, v in evidence.items()
              if k not in ("pending_llm", "llm_refinement")}
    return json.dumps(pruned, sort_keys=True, default=str)


def cache_key_for_op(op) -> str:
    """sha256-derived stable key for one operation's residual cache entry."""
    h = hashlib.sha256()
    h.update(getattr(op.kind, "value", str(op.kind)).encode("utf-8"))
    h.update(b"|")
    h.update((op.file or "").encode("utf-8"))
    h.update(b"|")
    h.update(f"{op.confidence:.3f}".encode("utf-8"))
    h.update(b"|")
    h.update(_norm(op.before).encode("utf-8"))
    h.update(b"|")
    h.update(_norm(op.after).encode("utf-8"))
    h.update(b"|")
    h.update(_norm_evidence(op.evidence).encode("utf-8"))
    return h.hexdigest()


def cache_path_for(op, *, cwd: Optional[Path] = None) -> Path:
    """Resolve the on-disk path for an op's cache entry."""
    cwd = (cwd or Path.cwd()).resolve()
    return cwd / ".sextant" / "cache" / "llm" / f"{cache_key_for_op(op)}.json"


# ---------------------------------------------------------------------------
# prompt assembly
# ---------------------------------------------------------------------------


PROMPT_HEADER = """You are Sextant's residual classifier. The deterministic rule
engine assigned the operation below a low confidence (< {threshold:.2f}).

Your job: confirm the candidate classification, OR correct it to a
better-fitting kind. Reply with ONE JSON object on a single line:

    {{"kind": "<operation-kind>", "confidence": <0..1>, "rationale": "<one sentence>"}}

Valid `kind` values: any operation kind already in Sextant
(rename-symbol, extract-function, move-symbol, move-file,
reorder-statements, reformat, comment-only, docstring-only, lint-fix,
invert-condition, add-import, remove-import, reorder-imports,
add-test, remove-test, change-signature, plain-edit, ...).

Do NOT invent new kinds. If unsure, return `plain-edit` at low
confidence — that's the honest answer.
"""


def build_residual_prompt(op, *, threshold: float = LOW_CONFIDENCE_THRESHOLD,
                          context_files: Optional[Dict[str, str]] = None) -> str:
    """Assemble the focused prompt for one residual op."""
    parts = [PROMPT_HEADER.format(threshold=threshold).rstrip(), ""]
    parts.append("## Candidate classification")
    parts.append(f"- kind: `{getattr(op.kind, 'value', op.kind)}`")
    parts.append(f"- confidence: {op.confidence:.3f}")
    parts.append(f"- file: `{op.file}`")
    parts.append(f"- summary: {op.summary}")
    if op.evidence:
        ev = {k: v for k, v in op.evidence.items()
              if k not in ("pending_llm", "llm_refinement")}
        if ev:
            parts.append("- evidence:")
            parts.append("  ```json")
            parts.append("  " + json.dumps(ev, sort_keys=True, default=str))
            parts.append("  ```")
    parts.append("")
    if op.before is not None or op.after is not None:
        parts.append("## Before/after snippets")
        parts.append("```")
        parts.append("--- before")
        parts.append(op.before or "")
        parts.append("--- after")
        parts.append(op.after or "")
        parts.append("```")
        parts.append("")
    if context_files:
        parts.append("## Adjacent context")
        for path, body in sorted(context_files.items()):
            parts.append(f"### `{path}`")
            parts.append("```")
            parts.append(body)
            parts.append("```")
        parts.append("")
    parts.append("Reply with the JSON object on a single line. Nothing else.")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# fold result back into op
# ---------------------------------------------------------------------------


def _apply_refinement(op, refinement: Dict[str, Any]) -> None:
    """Attach the LLM's verdict as an `llm_refinement` field on the op.

    We deliberately do NOT mutate `op.kind` or `op.confidence` — the
    deterministic core stays pure. Consumers (renderer, GUI, agents)
    inspect `evidence.llm_refinement` to see the residual classifier's
    proposal.
    """
    safe = {
        "kind": str(refinement.get("kind", "")) or None,
        "confidence": float(refinement.get("confidence", 0.0)),
        "rationale": str(refinement.get("rationale", "")),
        "source": "llm-residual",
    }
    op.evidence["llm_refinement"] = safe
    op.evidence["pending_llm"] = False


# ---------------------------------------------------------------------------
# main entry — run residual classifier across a list of pending ops
# ---------------------------------------------------------------------------


@dataclass
class ResidualOutcome:
    """Per-op result of `run_residual`. Returned for telemetry/tests."""
    cache_key: str
    cache_hit: bool
    runner: Optional[str]
    invoked: bool
    refined: bool
    error: Optional[str] = None


def run_residual(operations,
                 *, cwd: Optional[Path] = None,
                 runner_name: Optional[str] = None,
                 invoker=None,
                 detector=None,
                 write_cache: bool = True) -> List[ResidualOutcome]:
    """Run the residual classifier on every below-threshold op in
    `operations`. Mutates each refined op's `.evidence` in place.

    Cache hits are taken before any subprocess fires. Misses build the
    prompt, dispatch via the runner, parse the response, and write
    `.sextant/cache/llm/<sha>.json` on success.
    """
    from sextant.llm.runner import detect_runner as _detect, invoke_runner as _invoke

    detector = detector or _detect
    invoker = invoker or _invoke
    cwd = (cwd or Path.cwd()).resolve()

    pending = residual_route(operations)
    outcomes: List[ResidualOutcome] = []
    if not pending:
        return outcomes

    runner = detector(runner_name)
    # Even with no runner detected, we still tag/cache so the GUI's
    # "Discuss" button remains available — but we don't fabricate
    # refinements.

    for op in pending:
        key = cache_key_for_op(op)
        cache_path = cwd / ".sextant" / "cache" / "llm" / f"{key}.json"
        # Cache hit?
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                refinement = cached.get("refinement")
                if isinstance(refinement, dict):
                    _apply_refinement(op, refinement)
                    outcomes.append(ResidualOutcome(
                        cache_key=key, cache_hit=True,
                        runner=runner, invoked=False, refined=True,
                    ))
                    continue
            except (OSError, json.JSONDecodeError):
                pass  # fall through to a fresh invocation

        if not runner:
            outcomes.append(ResidualOutcome(
                cache_key=key, cache_hit=False, runner=None,
                invoked=False, refined=False,
                error="no runner detected (set SEXTANT_AGENT_RUNNER or install claude/codex/opencode)",
            ))
            continue

        prompt = build_residual_prompt(op)
        result = invoker(runner, prompt, expect_json=True)
        # Parse response — accept both bare envelope and "classification"-wrapped.
        refinement = None
        parsed = result.parsed
        if isinstance(parsed, dict):
            if "classification" in parsed and isinstance(parsed["classification"], dict):
                refinement = parsed["classification"]
            elif "kind" in parsed:
                refinement = parsed
        if refinement is None and result.stdout:
            # Last-ditch parse — first JSON object on the last line of stdout
            try:
                obj = json.loads(result.stdout.strip().splitlines()[-1])
                if isinstance(obj, dict):
                    if "classification" in obj and isinstance(obj["classification"], dict):
                        refinement = obj["classification"]
                    elif "kind" in obj:
                        refinement = obj
            except (json.JSONDecodeError, IndexError):
                refinement = None

        if refinement is not None:
            _apply_refinement(op, refinement)
            if write_cache:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({
                        "key": key,
                        "runner": result.runner,
                        "refinement": op.evidence["llm_refinement"],
                    }, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            outcomes.append(ResidualOutcome(
                cache_key=key, cache_hit=False, runner=result.runner,
                invoked=result.invoked, refined=True,
            ))
        else:
            outcomes.append(ResidualOutcome(
                cache_key=key, cache_hit=False, runner=result.runner,
                invoked=result.invoked, refined=False,
                error=result.error or "runner returned no parsable refinement",
            ))

    return outcomes
