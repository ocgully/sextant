"""tests/test_llm.py — phase 1E unit tests.

Covers:

* residual confidence routing — `pending_llm` flag set strictly below the
  LOW threshold; high/medium ops untouched.
* cache-key stability — same op shape → same sha; key changes when any
  identifying input changes; line-ending / trailing-whitespace drift
  does NOT change the key.
* runner detection — env-var, PATH probe, explicit choice, pseudo-runners.
* mock runner pattern — deterministic JSON envelope for CI.
* `run_residual` cache hit / miss + write.
* `build_discuss_bundle` determinism — same inputs → byte-identical
  artefacts.

Mock-runner protocol: tests never touch the network. The `mock` runner
in `diffsextant.llm.runner` returns a fixed JSON envelope; the residual
classifier folds that into `evidence.llm_refinement` so the rest of the
pipeline can be exercised end-to-end without an LLM.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from diffsextant.ops.base import Operation, OperationKind
from diffsextant.llm import (
    LOW_CONFIDENCE_THRESHOLD,
    cache_key_for_op,
    cache_path_for,
    detect_runner,
    invoke_runner,
    residual_route,
    run_residual,
    build_discuss_bundle,
)
from diffsextant.llm.residual import build_residual_prompt


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _op(kind: OperationKind, conf: float, *,
        file: str = "src/foo.py",
        before: str = "x = 1\n",
        after: str = "y = 1\n",
        evidence=None) -> Operation:
    return Operation(
        kind=kind,
        file=file,
        confidence=conf,
        summary=f"{kind.value} on {file}",
        before=before,
        after=after,
        evidence=dict(evidence or {}),
    )


# ---------------------------------------------------------------------------
# residual routing
# ---------------------------------------------------------------------------


class TestResidualRoute:
    def test_below_threshold_is_pending(self):
        op = _op(OperationKind.PLAIN_EDIT, 0.5)
        pending = residual_route([op])
        assert op.evidence["pending_llm"] is True
        assert op in pending

    def test_at_threshold_is_not_pending(self):
        op = _op(OperationKind.PLAIN_EDIT, LOW_CONFIDENCE_THRESHOLD)
        pending = residual_route([op])
        assert op.evidence["pending_llm"] is False
        assert pending == []

    def test_above_threshold_is_not_pending(self):
        op = _op(OperationKind.RENAME_SYMBOL, 0.95)
        pending = residual_route([op])
        assert op.evidence["pending_llm"] is False
        assert pending == []

    def test_mixed_population(self):
        ops = [
            _op(OperationKind.RENAME_SYMBOL, 0.95),       # high
            _op(OperationKind.EXTRACT_FUNCTION, 0.75),    # medium
            _op(OperationKind.PLAIN_EDIT, 0.55),          # low
            _op(OperationKind.PLAIN_EDIT, 0.30),          # low
        ]
        pending = residual_route(ops)
        assert len(pending) == 2
        assert all(p.confidence < LOW_CONFIDENCE_THRESHOLD for p in pending)


# ---------------------------------------------------------------------------
# cache key
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_same_op_same_key(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.5, before="x\n", after="y\n")
        b = _op(OperationKind.PLAIN_EDIT, 0.5, before="x\n", after="y\n")
        assert cache_key_for_op(a) == cache_key_for_op(b)

    def test_kind_change_invalidates(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.5)
        b = _op(OperationKind.RENAME_SYMBOL, 0.5)
        assert cache_key_for_op(a) != cache_key_for_op(b)

    def test_confidence_change_invalidates(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.50)
        b = _op(OperationKind.PLAIN_EDIT, 0.55)
        assert cache_key_for_op(a) != cache_key_for_op(b)

    def test_file_change_invalidates(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.5, file="a.py")
        b = _op(OperationKind.PLAIN_EDIT, 0.5, file="b.py")
        assert cache_key_for_op(a) != cache_key_for_op(b)

    def test_body_change_invalidates(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.5, before="x = 1\n")
        b = _op(OperationKind.PLAIN_EDIT, 0.5, before="x = 2\n")
        assert cache_key_for_op(a) != cache_key_for_op(b)

    def test_trailing_newline_drift_stable(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.5, before="x\n", after="y\n")
        b = _op(OperationKind.PLAIN_EDIT, 0.5, before="x", after="y")
        assert cache_key_for_op(a) == cache_key_for_op(b)

    def test_trailing_whitespace_stable(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.5, before="x = 1\n")
        b = _op(OperationKind.PLAIN_EDIT, 0.5, before="x = 1   \n")
        assert cache_key_for_op(a) == cache_key_for_op(b)

    def test_pending_llm_flag_does_not_affect_key(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.5,
                evidence={"pending_llm": False})
        b = _op(OperationKind.PLAIN_EDIT, 0.5,
                evidence={"pending_llm": True})
        # The routing flag is a state marker, not part of the op shape.
        assert cache_key_for_op(a) == cache_key_for_op(b)

    def test_evidence_change_invalidates(self):
        a = _op(OperationKind.PLAIN_EDIT, 0.5, evidence={"reason": "x"})
        b = _op(OperationKind.PLAIN_EDIT, 0.5, evidence={"reason": "y"})
        assert cache_key_for_op(a) != cache_key_for_op(b)

    def test_cache_path_under_dot_diffsextant(self, tmp_path):
        op = _op(OperationKind.PLAIN_EDIT, 0.5)
        p = cache_path_for(op, cwd=tmp_path)
        rel = p.relative_to(tmp_path.resolve())
        # New default is .diffsextant/. Legacy .sextant/ is still
        # auto-detected on read but the path resolver prefers the new dir
        # for fresh writes.
        assert rel.parts[:3] == (".diffsextant", "cache", "llm")
        assert rel.suffix == ".json"


# ---------------------------------------------------------------------------
# runner detection
# ---------------------------------------------------------------------------


class TestDetectRunner:
    def test_explicit_pseudo_runner(self):
        assert detect_runner("mock") == "mock"
        assert detect_runner("stdout") == "stdout"
        assert detect_runner("clipboard") == "clipboard"

    def test_explicit_real_runner_on_path(self):
        # Stub PATH so `claude` is "found".
        def lookup(name):
            return "/fake/bin/claude" if name == "claude" else None
        assert detect_runner("claude", path_lookup=lookup) == "claude"

    def test_explicit_real_runner_not_on_path(self):
        # Stub PATH so nothing is found.
        assert detect_runner("claude", path_lookup=lambda _: None) is None

    def test_env_var_pseudo(self):
        assert detect_runner(env={"DIFFSEXTANT_AGENT_RUNNER": "mock"},
                             path_lookup=lambda _: None) == "mock"

    def test_env_var_real_on_path(self):
        def lookup(name):
            return "/fake/bin/codex" if name == "codex" else None
        assert detect_runner(env={"DIFFSEXTANT_AGENT_RUNNER": "codex"},
                             path_lookup=lookup) == "codex"

    def test_env_var_real_not_on_path_returns_none(self):
        assert detect_runner(env={"DIFFSEXTANT_AGENT_RUNNER": "codex"},
                             path_lookup=lambda _: None) is None

    def test_legacy_env_var_still_honoured(self):
        # Backward-compat: the pre-rename `SEXTANT_AGENT_RUNNER` is still
        # accepted for one deprecation cycle so existing CI configs don't
        # break the day a project upgrades.
        assert detect_runner(env={"SEXTANT_AGENT_RUNNER": "mock"},
                             path_lookup=lambda _: None) == "mock"

    def test_new_env_var_wins_over_legacy(self):
        # When both are set, the canonical name takes precedence.
        assert detect_runner(env={"DIFFSEXTANT_AGENT_RUNNER": "mock",
                                  "SEXTANT_AGENT_RUNNER": "claude"},
                             path_lookup=lambda _: None) == "mock"

    def test_path_probe_prefers_claude(self):
        # All three on PATH; preference order is claude > codex > opencode.
        def lookup(name):
            return f"/fake/bin/{name}"
        assert detect_runner(env={}, path_lookup=lookup) == "claude"

    def test_path_probe_falls_through(self):
        def lookup(name):
            return "/fake/bin/opencode" if name == "opencode" else None
        assert detect_runner(env={}, path_lookup=lookup) == "opencode"

    def test_no_runner_anywhere(self):
        assert detect_runner(env={}, path_lookup=lambda _: None) is None


# ---------------------------------------------------------------------------
# mock runner — the "for tests + CI" pattern documented in residual.py
# ---------------------------------------------------------------------------


class TestMockRunner:
    def test_mock_returns_deterministic_envelope(self):
        r1 = invoke_runner("mock", "hello")
        r2 = invoke_runner("mock", "hello")
        assert r1.runner == "mock"
        assert r1.invoked is False
        assert r1.exit_code == 0
        assert r1.parsed["classification"]["kind"] == "plain-edit"
        # Same prompt → same JSON envelope.
        assert r1.stdout == r2.stdout

    def test_mock_envelope_carries_prompt_size(self):
        r = invoke_runner("mock", "hello world")
        assert r.parsed["prompt_chars"] == len("hello world")

    def test_stdout_runner_writes_to_stdout(self, capsys):
        r = invoke_runner("stdout", "this is the prompt")
        out = capsys.readouterr().out
        assert "this is the prompt" in out
        assert r.invoked is False
        assert r.exit_code == 0

    def test_explicit_subprocess_runner_for_real_agent(self, tmp_path):
        # When we pass a real-runner name (e.g. "claude") we do invoke
        # subprocess, but with a stub we can capture argv + return canned
        # output.
        recorded = {}

        class _FakeProc:
            def __init__(self, returncode, stdout, stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        def fake_run(argv, **kwargs):
            recorded["argv"] = argv
            recorded["kwargs"] = kwargs
            return _FakeProc(0, '{"kind": "plain-edit", "confidence": 0.6}')

        prompt_path = tmp_path / "prompt.md"
        r = invoke_runner("claude", "test prompt",
                          prompt_path=prompt_path,
                          expect_json=True,
                          subprocess_runner=fake_run)
        assert r.runner == "claude"
        assert r.invoked is True
        assert r.exit_code == 0
        assert r.parsed["kind"] == "plain-edit"
        # Argv shape is what the docstring promises.
        assert recorded["argv"][0] == "claude"
        assert "--print" in recorded["argv"]
        assert "--output-format" in recorded["argv"]
        assert str(prompt_path) in recorded["argv"]


# ---------------------------------------------------------------------------
# residual end-to-end with mock runner
# ---------------------------------------------------------------------------


class TestRunResidualWithMock:
    def test_refines_residual_writes_cache(self, tmp_path):
        op = _op(OperationKind.PLAIN_EDIT, 0.5)
        outcomes = run_residual([op],
                                cwd=tmp_path,
                                runner_name="mock")
        assert len(outcomes) == 1
        oc = outcomes[0]
        assert oc.refined is True
        assert oc.cache_hit is False
        # Refinement folded into evidence
        assert "llm_refinement" in op.evidence
        assert op.evidence["llm_refinement"]["kind"] == "plain-edit"
        assert op.evidence["pending_llm"] is False
        # Cache file written
        cp = cache_path_for(op, cwd=tmp_path)
        assert cp.exists()
        cached = json.loads(cp.read_text(encoding="utf-8"))
        assert cached["refinement"]["kind"] == "plain-edit"

    def test_cache_hit_skips_runner(self, tmp_path):
        op = _op(OperationKind.PLAIN_EDIT, 0.5)
        # First run populates cache
        run_residual([op], cwd=tmp_path, runner_name="mock")
        # Build a fresh op so evidence routing flag is reset
        op2 = _op(OperationKind.PLAIN_EDIT, 0.5)
        called = {"n": 0}

        def spy_invoke(*args, **kwargs):
            called["n"] += 1
            from diffsextant.llm.runner import invoke_runner as _real
            return _real(*args, **kwargs)

        outcomes = run_residual([op2],
                                cwd=tmp_path,
                                runner_name="mock",
                                invoker=spy_invoke)
        assert outcomes[0].cache_hit is True
        assert called["n"] == 0
        assert "llm_refinement" in op2.evidence

    def test_high_confidence_op_skipped(self, tmp_path):
        op = _op(OperationKind.RENAME_SYMBOL, 0.95)
        outcomes = run_residual([op], cwd=tmp_path, runner_name="mock")
        assert outcomes == []
        assert op.evidence.get("pending_llm") is False
        assert "llm_refinement" not in op.evidence

    def test_no_runner_no_refinement(self, tmp_path):
        op = _op(OperationKind.PLAIN_EDIT, 0.5)
        outcomes = run_residual([op],
                                cwd=tmp_path,
                                detector=lambda *a, **k: None)
        assert outcomes[0].refined is False
        assert outcomes[0].error is not None
        assert "llm_refinement" not in op.evidence


# ---------------------------------------------------------------------------
# discuss bundle determinism
# ---------------------------------------------------------------------------


class TestBuildDiscussBundle:
    def _fake_result(self):
        from diffsextant.tree_delta import DiffResult
        from diffsextant.git_context import GitContext
        op = _op(OperationKind.RENAME_SYMBOL, 0.92,
                 file="src/auth.py", before="user_id", after="account_id")
        change = type("FakeChange", (), {
            "path_before": "src/auth.py",
            "path_after": "src/auth.py",
            "language": "python",
            "is_new": False,
            "is_deleted": False,
            "is_renamed": False,
            "path": "src/auth.py",
        })()
        gc = GitContext(cwd=Path("."), is_repo=True, branch="feat/auth")
        return DiffResult(operations=[op], changes=[change], git_context=gc)

    def test_bundle_files_exist(self, tmp_path, monkeypatch):
        # Avoid `git diff` shelling out by chdir'ing to tmp_path
        monkeypatch.chdir(tmp_path)
        result = self._fake_result()
        bundle = build_discuss_bundle(
            result, "HEAD~1", "HEAD",
            cwd=tmp_path,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        assert bundle.context_path.exists()
        assert bundle.operations_path.exists()
        assert bundle.diff_path.exists()
        assert bundle.prompt_path.exists()
        # Session-id is stable across calls
        bundle2 = build_discuss_bundle(
            result, "HEAD~1", "HEAD",
            cwd=tmp_path,
            generated_at="2026-01-01T00:00:00+00:00",
        )
        assert bundle.session_id == bundle2.session_id

    def test_bundle_byte_identical_with_pinned_timestamp(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = self._fake_result()
        b1 = build_discuss_bundle(result, "HEAD~1", "HEAD",
                                  cwd=tmp_path,
                                  generated_at="2026-01-01T00:00:00+00:00")
        ctx1 = b1.context_path.read_bytes()
        ops1 = b1.operations_path.read_bytes()
        prompt1 = b1.prompt_path.read_bytes()
        # Re-run — same inputs, same outputs.
        b2 = build_discuss_bundle(result, "HEAD~1", "HEAD",
                                  cwd=tmp_path,
                                  generated_at="2026-01-01T00:00:00+00:00")
        assert b2.context_path.read_bytes() == ctx1
        assert b2.operations_path.read_bytes() == ops1
        assert b2.prompt_path.read_bytes() == prompt1

    def test_session_id_varies_with_range(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = self._fake_result()
        a = build_discuss_bundle(result, "HEAD~1", "HEAD", cwd=tmp_path,
                                 generated_at="2026-01-01T00:00:00+00:00")
        b = build_discuss_bundle(result, "main", "feat/x", cwd=tmp_path,
                                 generated_at="2026-01-01T00:00:00+00:00")
        assert a.session_id != b.session_id


# ---------------------------------------------------------------------------
# prompt assembly
# ---------------------------------------------------------------------------


class TestBuildResidualPrompt:
    def test_prompt_mentions_kind_and_confidence(self):
        op = _op(OperationKind.PLAIN_EDIT, 0.55,
                 before="x = 1\n", after="y = 1\n")
        prompt = build_residual_prompt(op)
        assert "plain-edit" in prompt
        assert "0.550" in prompt
        assert "JSON object on a single line" in prompt
        assert "x = 1" in prompt
        assert "y = 1" in prompt
