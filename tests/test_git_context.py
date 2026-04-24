"""Git-context enrichment — commit-message priors feed classifier bumps."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sextant.git_context import GitContext, collect, KEYWORD_PRIORS


def _sh(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    _sh(["git", "init", "-q", "-b", "main"], tmp_path)
    _sh(["git", "config", "user.email", "test@example.com"], tmp_path)
    _sh(["git", "config", "user.name", "Test"], tmp_path)
    (tmp_path / "f.py").write_text("def foo(): return 1\n", encoding="utf-8")
    _sh(["git", "add", "-A"], tmp_path)
    _sh(["git", "commit", "-q", "-m", "initial"], tmp_path)
    return tmp_path


def test_collect_not_a_repo(tmp_path):
    ctx = collect(tmp_path)
    assert ctx.is_repo is False
    assert ctx.branch is None


def test_collect_branch_and_messages(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "f.py").write_text("def bar(): return 2\n", encoding="utf-8")
    _sh(["git", "add", "-A"], repo)
    _sh(["git", "commit", "-q", "-m", "refactor: rename foo to bar"], repo)

    ctx = collect(repo, ref1="HEAD~1", ref2="HEAD")
    assert ctx.is_repo is True
    assert ctx.branch == "main"
    assert ctx.commit_messages, "commit_messages should be populated"
    bodies = " ".join(m["body"] for m in ctx.commit_messages)
    assert "rename" in bodies


def test_prior_for_rename(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "f.py").write_text("def bar(): return 2\n", encoding="utf-8")
    _sh(["git", "add", "-A"], repo)
    _sh(["git", "commit", "-q", "-m", "refactor: rename foo to bar"], repo)

    ctx = collect(repo, ref1="HEAD~1", ref2="HEAD")
    prior = ctx.prior_for("rename-symbol")
    assert prior > 0, f"commit msg has 'rename' — prior should fire, got {prior}"
    assert prior <= 0.3


def test_prior_for_unrelated_kind_is_zero(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "f.py").write_text("def bar(): return 2\n", encoding="utf-8")
    _sh(["git", "add", "-A"], repo)
    _sh(["git", "commit", "-q", "-m", "completely unrelated message"], repo)
    ctx = collect(repo, ref1="HEAD~1", ref2="HEAD")
    assert ctx.prior_for("rename-symbol") == 0


def test_keyword_priors_coverage():
    # every registered kind has at least one pattern
    for kind, patterns in KEYWORD_PRIORS.items():
        assert patterns, f"{kind} has no keyword patterns"
