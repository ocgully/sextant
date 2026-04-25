"""Read .git for branch provenance during an in-flight merge.

The merge driver sees only the four arguments git passes (%O %A %B %P).
The CLI inspector sees a worktree mid-merge. Both want the names of
the two sides ("ours-branch" / "theirs-branch"). Git stashes that in
``.git/MERGE_HEAD``, ``.git/MERGE_MSG``, and ``.git/HEAD``.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from sextant.conflict.types import BranchProvenance


def _run_git(args, cwd: Path) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd), check=False,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def _git_dir(cwd: Path) -> Optional[Path]:
    out = _run_git(["rev-parse", "--git-dir"], cwd)
    if not out:
        return None
    p = Path(out.strip())
    return p if p.is_absolute() else (cwd / p).resolve()


def read_branch_provenance(cwd: Path | str) -> BranchProvenance:
    """Best-effort. Never raises. Missing fields stay None."""
    cwd = Path(cwd)
    prov = BranchProvenance()
    gd = _git_dir(cwd)
    if gd is None or not gd.exists():
        return prov

    # State
    if (gd / "MERGE_HEAD").exists():
        prov.state = "merge"
    elif (gd / "CHERRY_PICK_HEAD").exists():
        prov.state = "cherry-pick"
    elif (gd / "REBASE_HEAD").exists() or (gd / "rebase-merge").exists() \
            or (gd / "rebase-apply").exists():
        prov.state = "rebase"

    # Ours = current HEAD branch + sha
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch:
        prov.ours_branch = branch.strip()
    head_sha = _run_git(["rev-parse", "HEAD"], cwd)
    if head_sha:
        prov.ours_sha = head_sha.strip()

    # Theirs = MERGE_HEAD sha (if present)
    mh = gd / "MERGE_HEAD"
    if mh.exists():
        try:
            prov.theirs_sha = mh.read_text(encoding="utf-8").strip().splitlines()[0]
        except OSError:
            pass
        # Try to recover the symbolic name from MERGE_MSG, e.g.:
        #   "Merge branch 'feat/billing'"
        mm = gd / "MERGE_MSG"
        if mm.exists():
            try:
                msg = mm.read_text(encoding="utf-8")
                m = re.search(r"Merge branch '([^']+)'", msg)
                if m:
                    prov.theirs_branch = m.group(1)
                else:
                    m = re.search(r"Merge remote-tracking branch '([^']+)'", msg)
                    if m:
                        prov.theirs_branch = m.group(1)
            except OSError:
                pass

    # Merge base
    if prov.ours_sha and prov.theirs_sha:
        mb = _run_git(["merge-base", prov.ours_sha, prov.theirs_sha], cwd)
        if mb:
            prov.base_sha = mb.strip()

    return prov
