"""Tests for diffsextant/git_driver.py — install / uninstall idempotency,
sentinel detection, .gitattributes merge, scoped config, --git-driver-mode
protocol roundtrip.

These tests run against ephemeral git repos so they don't pollute the
user's actual config. We never invoke `--scope user` install/uninstall
end-to-end (that would touch ~/.gitconfig); the user-scope code path is
exercised through unit-level helpers only.
"""
from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest

from diffsextant import git_driver as gd


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _git(args, cwd, check=True):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Empty git repo with a deterministic identity for commits."""
    _git(["init", "-q", "-b", "main"], cwd=tmp_path)
    _git(["config", "user.email", "test@example.com"], cwd=tmp_path)
    _git(["config", "user.name", "Test"], cwd=tmp_path)
    _git(["config", "commit.gpgsign", "false"], cwd=tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# build / parse helpers
# ---------------------------------------------------------------------------


def test_build_attr_block_includes_sentinels():
    block = gd._build_attr_block(("*.py", "*.ts"))
    assert block.startswith(gd.SENTINEL_OPEN + "\n")
    assert block.rstrip().endswith(gd.SENTINEL_CLOSE)
    assert "*.py" in block and "diff=sextant" in block


def test_strip_managed_block_removes_only_block():
    text = (
        "*.bin binary\n"
        "\n"
        + gd._build_attr_block(("*.py",))
        + "*.lock linguist-generated\n"
    )
    stripped = gd._strip_managed_block(text)
    assert gd.SENTINEL_OPEN not in stripped
    assert gd.SENTINEL_CLOSE not in stripped
    assert "*.bin binary" in stripped
    assert "*.lock linguist-generated" in stripped


def test_has_managed_block_detects_sentinel():
    assert not gd._has_managed_block("*.bin binary\n")
    assert gd._has_managed_block(gd._build_attr_block(("*.py",)))


# ---------------------------------------------------------------------------
# install (repo scope)
# ---------------------------------------------------------------------------


def test_install_writes_config_and_attributes(tmp_repo):
    out = io.StringIO()
    rc = gd.install(scope="repo", cwd=tmp_repo, stream=out)
    assert rc == 0

    # git config: diff.sextant.command exists with our value
    cmd = _git(["config", "--local", "--get", "diff.sextant.command"],
               cwd=tmp_repo).stdout.strip()
    assert cmd == gd.DRIVER_COMMAND
    binary = _git(["config", "--local", "--get", "diff.sextant.binary"],
                  cwd=tmp_repo).stdout.strip()
    assert binary == "false"

    # .gitattributes contains the sentinel block
    text = (tmp_repo / ".gitattributes").read_text(encoding="utf-8")
    assert gd.SENTINEL_OPEN in text
    assert gd.SENTINEL_CLOSE in text
    for pat in gd.DEFAULT_ATTR_PATTERNS:
        assert pat in text


def test_install_is_idempotent(tmp_repo):
    out = io.StringIO()
    gd.install(scope="repo", cwd=tmp_repo, stream=out)
    text_after_first = (tmp_repo / ".gitattributes").read_text(encoding="utf-8")

    out2 = io.StringIO()
    rc = gd.install(scope="repo", cwd=tmp_repo, stream=out2)
    assert rc == 0
    text_after_second = (tmp_repo / ".gitattributes").read_text(encoding="utf-8")

    # File is byte-identical after the second install
    assert text_after_first == text_after_second
    # And the second-run output reports the no-op
    msg = out2.getvalue()
    assert "skipped" in msg or "already" in msg


def test_install_preserves_existing_gitattributes(tmp_repo):
    user_block = "*.bin binary\n*.lock linguist-generated\n"
    (tmp_repo / ".gitattributes").write_text(user_block, encoding="utf-8")

    gd.install(scope="repo", cwd=tmp_repo, stream=io.StringIO())
    text = (tmp_repo / ".gitattributes").read_text(encoding="utf-8")

    # User content is preserved verbatim, sextant block is appended
    assert "*.bin binary" in text
    assert "*.lock linguist-generated" in text
    assert gd.SENTINEL_OPEN in text
    # Order: user content first, then our block
    assert text.index("*.bin binary") < text.index(gd.SENTINEL_OPEN)


def test_install_in_non_repo_fails(tmp_path):
    # An arbitrary tmpdir without `git init` shouldn't accept --scope repo
    out = io.StringIO()
    rc = gd.install(scope="repo", cwd=tmp_path, stream=out)
    assert rc == 2


# ---------------------------------------------------------------------------
# uninstall (repo scope)
# ---------------------------------------------------------------------------


def test_uninstall_after_install_is_clean(tmp_repo):
    gd.install(scope="repo", cwd=tmp_repo, stream=io.StringIO())
    out = io.StringIO()
    rc = gd.uninstall(scope="repo", cwd=tmp_repo, stream=out)
    assert rc == 0

    # git config is clean
    proc = _git(["config", "--local", "--get", "diff.sextant.command"],
                cwd=tmp_repo, check=False)
    assert proc.returncode == 1  # key not present

    # .gitattributes either gone (if it was empty before us) or no sextant block
    attrs = tmp_repo / ".gitattributes"
    if attrs.exists():
        text = attrs.read_text(encoding="utf-8")
        assert gd.SENTINEL_OPEN not in text


def test_uninstall_is_surgical(tmp_repo):
    user_block = "*.bin binary\n*.lock linguist-generated\n"
    (tmp_repo / ".gitattributes").write_text(user_block, encoding="utf-8")

    gd.install(scope="repo", cwd=tmp_repo, stream=io.StringIO())
    gd.uninstall(scope="repo", cwd=tmp_repo, stream=io.StringIO())

    text = (tmp_repo / ".gitattributes").read_text(encoding="utf-8")
    # User content survived
    assert "*.bin binary" in text
    assert "*.lock linguist-generated" in text
    # Sextant block is gone
    assert gd.SENTINEL_OPEN not in text
    assert gd.SENTINEL_CLOSE not in text
    assert "diff=sextant" not in text


def test_uninstall_when_nothing_installed_is_noop(tmp_repo):
    out = io.StringIO()
    rc = gd.uninstall(scope="repo", cwd=tmp_repo, stream=out)
    assert rc == 0
    msg = out.getvalue()
    assert "already clean" in msg


# ---------------------------------------------------------------------------
# scope plumbing (config-flag mapping)
# ---------------------------------------------------------------------------


def test_scope_repo_uses_local_flag():
    s = gd._scope("repo")
    assert s.config_flag == "--local"
    assert s.touches_attrs is True


def test_scope_user_uses_global_flag():
    s = gd._scope("user")
    assert s.config_flag == "--global"
    assert s.touches_attrs is False


def test_scope_unknown_raises():
    with pytest.raises(ValueError):
        gd._scope("system")


# ---------------------------------------------------------------------------
# --git-driver-mode protocol roundtrip
# ---------------------------------------------------------------------------


def test_git_driver_invocation_from_argv_happy_path():
    inv = gd.GitDriverInvocation.from_argv([
        "lib/foo.py",
        "/tmp/old-blob",
        "abc123",
        "100644",
        "/tmp/new-blob",
        "def456",
        "100644",
    ])
    assert inv.path == "lib/foo.py"
    assert inv.old_file == "/tmp/old-blob"
    assert inv.new_hex == "def456"


def test_git_driver_invocation_too_few_args_raises():
    with pytest.raises(ValueError, match="7 positional"):
        gd.GitDriverInvocation.from_argv(["lib/foo.py", "/tmp/old"])


def test_render_driver_invocation_classifies_pair(tmp_path):
    # Write before/after blobs to disk and run the driver-mode pipeline
    old = tmp_path / "old.py"
    new = tmp_path / "new.py"
    old.write_text("def foo():\n    return 1\n", encoding="utf-8")
    new.write_text("def foo():\n    return 2\n", encoding="utf-8")
    inv = gd.GitDriverInvocation(
        path="lib/foo.py",
        old_file=str(old), old_hex="aaa", old_mode="100644",
        new_file=str(new), new_hex="bbb", new_mode="100644",
    )
    out = io.StringIO()
    rc = gd.render_driver_invocation(inv, fmt="text", stream=out)
    assert rc == 0
    rendered = out.getvalue()
    # Rendered text mentions the path so reviewers know which file
    assert "lib/foo.py" in rendered or "foo.py" in rendered


def test_render_driver_invocation_handles_dev_null(tmp_path):
    # New file (no old side) — git would pass /dev/null for old
    new = tmp_path / "new.py"
    new.write_text("def bar(): return 1\n", encoding="utf-8")
    inv = gd.GitDriverInvocation(
        path="lib/bar.py",
        old_file="/dev/null", old_hex="0" * 40, old_mode="000000",
        new_file=str(new), new_hex="bbb", new_mode="100644",
    )
    out = io.StringIO()
    rc = gd.render_driver_invocation(inv, fmt="text", stream=out)
    assert rc == 0


def test_cli_diff_git_driver_mode_dispatches(tmp_path):
    """The argparse layer reshapes argv: ref1=path, ref2=old-file,
    files=[old-hex, old-mode, new-file, new-hex, new-mode]. Verify the
    dispatch in cli.py wires through to git_driver."""
    from diffsextant.cli import build_parser, cmd_diff

    old = tmp_path / "old.py"
    new = tmp_path / "new.py"
    old.write_text("def foo(): return 1\n", encoding="utf-8")
    new.write_text("def foo(): return 2\n", encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args([
        "diff", "--git-driver-mode",
        "lib/foo.py",
        str(old), "abc", "100644",
        str(new), "def", "100644",
    ])
    assert args.git_driver_mode is True
    rc = cmd_diff(args)
    assert rc == 0
