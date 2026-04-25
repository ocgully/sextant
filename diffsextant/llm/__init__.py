"""LLM residual classifier + agent-session integration (phase 1E).

Sextant does NOT embed a chat client and does NOT require ANTHROPIC_API_KEY.
The pattern is: package the diff context + classified ops as a context
bundle on disk, then trigger the user's existing agent runner (Claude
Code primary; Codex / OpenCode secondary).

Public surface:

    from diffsextant.llm import (
        # residual classifier — refines low-confidence ops only
        residual_route,
        residual_threshold,
        run_residual,

        # discuss — assembles a conversation bundle for the user's agent
        build_discuss_bundle,
        discuss,

        # runner — detects + invokes the user's agent on PATH
        detect_runner,
        invoke_runner,
        RunnerResult,
    )

The LLM is *additive*: it never overrides high/medium-confidence
classifications. It only refines residuals (`pending_llm`) and only
when the user opts in with `--llm`.
"""
from __future__ import annotations

from diffsextant.llm.residual import (
    LOW_CONFIDENCE_THRESHOLD,
    residual_route,
    residual_threshold,
    run_residual,
    cache_path_for,
    cache_key_for_op,
)
from diffsextant.llm.discuss import (
    build_discuss_bundle,
    discuss,
    bundle_path_for,
)
from diffsextant.llm.runner import (
    detect_runner,
    invoke_runner,
    RunnerResult,
    RUNNER_CHOICES,
)

__all__ = [
    "LOW_CONFIDENCE_THRESHOLD",
    "residual_route",
    "residual_threshold",
    "run_residual",
    "cache_path_for",
    "cache_key_for_op",
    "build_discuss_bundle",
    "discuss",
    "bundle_path_for",
    "detect_runner",
    "invoke_runner",
    "RunnerResult",
    "RUNNER_CHOICES",
]
