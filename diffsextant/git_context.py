"""Git-context enrichment (plan §4.7).

Every command runs inside a worktree pulls a situational snapshot:
branch, commit messages for the diff range, adjacent commits, cherry-
pick / rebase / merge state, blame for touched regions. Failure-
tolerant: any individual slice that fails is elided silently.

The commit-message slice feeds the classifier as a prior. Keyword
matches bias confidence but never invent a classification on their own.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# Keyword priors — §4.7. Values are confidence-nudge amounts.
#   Positive number = bias a matching classifier's confidence UP.
#   The classifier multiplies `priors.get(kind, 0.0)` into its weight.
KEYWORD_PRIORS: Dict[str, Dict[str, float]] = {
    # kind-str -> {regex-source: bump}
    "rename-symbol": {
        r"\brename(?:d|s|ing)?\b": 0.15,
        r"\brefactor\b": 0.05,
    },
    "extract-function": {
        r"\bextract(?:ed|s|ing)?\b": 0.15,
        r"\bfactor(?:ed)?\s+out\b": 0.15,
        r"\brefactor\b": 0.05,
    },
    "move-file": {
        r"\bmove(?:d|s|ing)?\b": 0.15,
        r"\brelocate(?:d|s|ing)?\b": 0.15,
    },
    "move-symbol": {
        r"\bmove(?:d|s|ing)?\b": 0.10,
    },
    "reformat": {
        r"\bformat(?:ted|ting)?\b": 0.20,
        r"\blint\b": 0.15,
        r"\bprettier\b": 0.20,
        r"\brustfmt\b": 0.20,
        r"\bblack\b": 0.20,
        r"\bgofmt\b": 0.20,
        r"\bautopep8\b": 0.15,
    },
    "lint-fix": {
        r"\blint\b": 0.20,
        r"\beslint\b": 0.20,
        r"\bruff\b": 0.20,
        r"\bclippy\b": 0.20,
    },
    "change-signature": {
        r"\bsignature\b": 0.15,
        r"\bparam(?:eter)?s?\b": 0.10,
    },
    "invert-condition": {
        r"\binvert(?:ed)?\b": 0.15,
        r"\bnegate(?:d)?\b": 0.10,
    },
    "add-import": {
        r"\bimport\b": 0.05,
    },
    "remove-import": {
        r"\bunused\s+imports?\b": 0.15,
        r"\bremove\s+imports?\b": 0.10,
    },
}


# Bias flags — non-kind-specific nudges from commit msg.
BIAS_FLAGS = {
    "wip":       re.compile(r"\b(wip|temp|debug|hack|scratch|broken)\b", re.I),
    "fix":       re.compile(r"\b(fix(?:es|ed)?|bug|regression)\b", re.I),
    "risk_up":   re.compile(r"\b(security|critical|urgent|hotfix)\b", re.I),
}


@dataclass
class GitContext:
    """Captured once per diff run; shared across classifiers."""
    cwd: Path
    is_repo: bool
    branch: Optional[str] = None
    upstream: Optional[str] = None
    commit_range: Optional[tuple[str, str]] = None  # (ref1, ref2)
    commit_messages: List[Dict[str, str]] = field(default_factory=list)
    adjacent_before: Optional[Dict[str, str]] = None
    adjacent_after: Optional[Dict[str, str]] = None
    pick_state: Optional[str] = None  # cherry-pick | rebase | merge | None
    bias_flags: Dict[str, bool] = field(default_factory=dict)

    def prior_for(self, kind: str) -> float:
        """Sum of keyword-prior bumps for `kind` across all commit msgs."""
        bumps = KEYWORD_PRIORS.get(kind)
        if not bumps:
            return 0.0
        corpus = " ".join(m.get("body", "") for m in self.commit_messages)
        if not corpus:
            return 0.0
        total = 0.0
        for pattern, delta in bumps.items():
            if re.search(pattern, corpus, re.I):
                total += delta
        # cap at 0.3 so a spammy message can't force high-confidence on its own
        return min(total, 0.3)

    def prior_description(self, kind: str) -> str:
        """Human explanation of which keywords matched."""
        bumps = KEYWORD_PRIORS.get(kind)
        if not bumps:
            return ""
        corpus = " ".join(m.get("body", "") for m in self.commit_messages)
        matched = []
        for pattern, _delta in bumps.items():
            if re.search(pattern, corpus, re.I):
                matched.append(pattern.strip(r"\b").replace(r"\s+", " "))
        return ", ".join(matched)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["cwd"] = str(self.cwd)
        d["commit_range"] = list(self.commit_range) if self.commit_range else None
        return d


def _run_git(args: Sequence[str], cwd: Path, check: bool = False) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=check,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def in_git_repo(cwd: Path) -> bool:
    out = _run_git(["rev-parse", "--is-inside-work-tree"], cwd)
    return bool(out and out.strip() == "true")


def collect(cwd: Path, ref1: Optional[str] = None, ref2: Optional[str] = None) -> GitContext:
    """Build the full context snapshot. Never raises."""
    ctx = GitContext(cwd=cwd, is_repo=in_git_repo(cwd))
    if not ctx.is_repo:
        return ctx

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch:
        ctx.branch = branch.strip()

    upstream = _run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd)
    if upstream:
        ctx.upstream = upstream.strip()

    # Pick state
    git_dir = _run_git(["rev-parse", "--git-dir"], cwd)
    if git_dir:
        gd = (cwd / git_dir.strip()).resolve() if not Path(git_dir.strip()).is_absolute() else Path(git_dir.strip())
        if (gd / "CHERRY_PICK_HEAD").exists():
            ctx.pick_state = "cherry-pick"
        elif (gd / "MERGE_HEAD").exists():
            ctx.pick_state = "merge"
        elif (gd / "REBASE_HEAD").exists() or (gd / "rebase-merge").exists() or (gd / "rebase-apply").exists():
            ctx.pick_state = "rebase"

    # Commit messages for range
    if ref1 and ref2:
        ctx.commit_range = (ref1, ref2)
        # "between ref1 and ref2" — handles ref1==ref2 case (single commit)
        log_range = f"{ref1}..{ref2}" if ref1 != ref2 else ref2
        ctx.commit_messages = _log_messages(cwd, log_range)
        if not ctx.commit_messages and ref1 != ref2:
            # Fallback: describe the end commits themselves
            ctx.commit_messages = _log_messages(cwd, ref2, n=1)
        ctx.adjacent_before = _adjacent(cwd, ref1, direction="before")
        ctx.adjacent_after = _adjacent(cwd, ref2, direction="after")

    # Bias flags from aggregate commit corpus
    corpus = " ".join(m.get("body", "") for m in ctx.commit_messages)
    for flag, pattern in BIAS_FLAGS.items():
        ctx.bias_flags[flag] = bool(pattern.search(corpus))

    return ctx


def _log_messages(cwd: Path, rev: str, n: Optional[int] = None) -> List[Dict[str, str]]:
    fmt = "%H%x1f%s%x1f%b%x1e"
    args = ["log", f"--format={fmt}"]
    if n is not None:
        args.append(f"-{n}")
    args.append(rev)
    args.append("--")
    out = _run_git(args, cwd)
    if not out:
        return []
    messages = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split("\x1f")
        if len(parts) < 3:
            continue
        sha, subject, body = parts[0], parts[1], parts[2]
        messages.append({
            "sha": sha.strip(),
            "subject": subject.strip(),
            "body": (subject + "\n\n" + body).strip(),
        })
    return messages


def _adjacent(cwd: Path, ref: str, direction: str) -> Optional[Dict[str, str]]:
    """One commit before (parent) or after (first-child on HEAD's line)."""
    if direction == "before":
        target = f"{ref}^"
    else:
        # "commit after ref" requires knowing which branch we're on; use
        # `git log HEAD --ancestry-path ref..HEAD -1 --reverse`
        out = _run_git(
            ["log", "--ancestry-path", "--reverse", "--format=%H", f"{ref}..HEAD"],
            cwd,
        )
        if not out:
            return None
        first = out.strip().splitlines()
        if not first:
            return None
        target = first[0]

    msgs = _log_messages(cwd, target, n=1)
    return msgs[0] if msgs else None


def blame_churn(cwd: Path, path: str, line_start: int, line_end: int) -> Optional[int]:
    """Rough churn score: number of distinct commits touching the region."""
    out = _run_git(
        ["blame", "-L", f"{line_start},{line_end}", "--porcelain", path],
        cwd,
    )
    if not out:
        return None
    seen = set()
    for line in out.splitlines():
        # porcelain commit lines are 40-hex sha at the start of the line
        if len(line) >= 40 and all(c in "0123456789abcdef" for c in line[:40]):
            seen.add(line[:40])
    return len(seen) if seen else None
