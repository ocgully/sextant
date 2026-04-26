"""Shared test helpers — tmp git repo construction + fixture discovery.

Used by tests/test_fixtures.py to materialise a fixture's `before/` +
`after/` trees as two commits in a throwaway repo, then run DiffSextant's
classifier against them.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional

import pytest


# ---------------------------------------------------------------------------
# tmp git repo construction
# ---------------------------------------------------------------------------


def _sh(args: List[str], cwd: Path) -> None:
    """Run a git command in `cwd`. Raise on failure (the test should fail
    loud; tmp-repo construction shouldn't ever silently break)."""
    subprocess.run(
        args, cwd=str(cwd), check=True, capture_output=True, text=True,
    )


def init_repo(tmp_path: Path, *, default_branch: str = "main") -> Path:
    """Initialise a fresh git repo with deterministic identity. Returns
    the repo path."""
    _sh(["git", "init", "-q", "-b", default_branch], tmp_path)
    _sh(["git", "config", "user.email", "test@example.com"], tmp_path)
    _sh(["git", "config", "user.name", "Test"], tmp_path)
    # Disable signing + GPG so this works on any dev machine
    _sh(["git", "config", "commit.gpgsign", "false"], tmp_path)
    return tmp_path


def _copy_tree_into(src: Path, dst: Path) -> None:
    """Recursively copy `src` into existing `dst`, preserving structure."""
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.read_bytes())


def _wipe_worktree(repo: Path) -> None:
    """Remove every tracked file (but keep .git/)."""
    for child in repo.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def materialise_fixture(repo: Path, before_dir: Path, after_dir: Path,
                        commit_msg: str = "fixture change") -> tuple[str, str]:
    """Lay down `before_dir` -> commit -> wipe -> lay down `after_dir` ->
    commit. Returns (ref_before, ref_after) = ("HEAD~1", "HEAD")."""
    init_repo(repo)
    if before_dir.exists():
        _copy_tree_into(before_dir, repo)
    # Even if `before/` is empty, we need a baseline commit so HEAD~1 exists.
    # Drop a sentinel that we then remove in the after-commit so the diff
    # remains accurate.
    sentinel = repo / ".diffsextant-fixture-sentinel"
    has_before_files = any(repo.iterdir()) and any(
        c.name != ".git" for c in repo.iterdir()
    )
    if not has_before_files:
        sentinel.write_text("placeholder\n", encoding="utf-8")
    _sh(["git", "add", "-A"], repo)
    _sh(["git", "commit", "-q", "-m", "before"], repo)

    # Replace tree with after/
    _wipe_worktree(repo)
    if after_dir.exists():
        _copy_tree_into(after_dir, repo)
    _sh(["git", "add", "-A"], repo)
    # If there's nothing to commit, force an empty commit so HEAD differs
    rc = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(repo), capture_output=True,
    )
    if rc.returncode == 0:
        _sh(["git", "commit", "-q", "--allow-empty", "-m", commit_msg], repo)
    else:
        _sh(["git", "commit", "-q", "-m", commit_msg], repo)
    return ("HEAD~1", "HEAD")


# ---------------------------------------------------------------------------
# fixture discovery
# ---------------------------------------------------------------------------


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def iter_fixture_dirs() -> Iterable[Path]:
    """Yield every fixture directory under tests/fixtures/<category>/<name>/.

    A directory qualifies as a fixture if it has a README.md (every fixture
    must document itself) and at least one of {before/, after/}.
    """
    if not FIXTURES_ROOT.exists():
        return
    for category in sorted(FIXTURES_ROOT.iterdir()):
        if not category.is_dir():
            continue
        for fixture in sorted(category.iterdir()):
            if not fixture.is_dir():
                continue
            if not (fixture / "README.md").exists():
                continue
            if not ((fixture / "before").exists() or (fixture / "after").exists()):
                continue
            yield fixture


# ---------------------------------------------------------------------------
# pytest CLI: --update-snapshots
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots", action="store_true", default=False,
        help="Rewrite tests/fixtures/*/expected.json from current DiffSextant output.",
    )


@pytest.fixture
def update_snapshots(request) -> bool:
    """True when the user passed --update-snapshots OR set
    DIFFSEXTANT_UPDATE_SNAPSHOTS=1 (legacy SEXTANT_UPDATE_SNAPSHOTS=1
    accepted for one cycle)."""
    if request.config.getoption("--update-snapshots"):
        return True
    for var in ("DIFFSEXTANT_UPDATE_SNAPSHOTS", "SEXTANT_UPDATE_SNAPSHOTS"):
        if os.environ.get(var, "").lower() in ("1", "true", "yes"):
            return True
    return False
