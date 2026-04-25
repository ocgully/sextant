"""`sextant discuss` — assemble a context bundle and trigger the user's agent.

The "discuss" flow is deliberately lightweight. Sextant doesn't run a
chat client; it produces:

    .sextant/conversations/<session-id>/
        context.md          ← human-readable narrative
        operations.json     ← raw classifier output (round-trippable)
        diff.patch          ← raw `git diff` for the range
        prompt.md           ← seed prompt the agent sees first

…then either invokes the user's agent CLI (claude / codex / opencode)
or copies the prompt to the clipboard. The session-id is a stable
hash of (cwd, ref1, ref2) so re-running over the same range reuses
the directory.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# session id
# ---------------------------------------------------------------------------


def _session_id(cwd: Path, ref1: str, ref2: str) -> str:
    """Stable per-range id. 12 hex chars → readable + collision-safe enough
    for the conversation-bundle namespace."""
    h = hashlib.sha256()
    h.update(str(cwd.resolve()).encode("utf-8"))
    h.update(b"\x00")
    h.update(ref1.encode("utf-8"))
    h.update(b"\x00")
    h.update(ref2.encode("utf-8"))
    return h.hexdigest()[:12]


def bundle_path_for(cwd: Path, ref1: str, ref2: str) -> Path:
    """Resolve the on-disk location for a discuss bundle."""
    sid = _session_id(cwd, ref1, ref2)
    return (cwd / ".sextant" / "conversations" / sid).resolve()


# ---------------------------------------------------------------------------
# bundle assembly
# ---------------------------------------------------------------------------


SEED_PROMPT = """You are reviewing a Sextant-classified diff with the user.

Sextant has already done the deterministic work — the operations file
attached lists every classified change with confidence + evidence.
Your job is to discuss it: surface implications, spot missed
intent, and answer follow-ups.

Open with a short summary (3-5 bullets max) of the highest-impact
operations and any low-confidence residuals worth a closer look.
Keep technical accuracy over prose density. Cite file paths verbatim.

Bundle layout (everything is on disk under
`.sextant/conversations/<session-id>/`):

  - `context.md`     — this file's prose narrative + git context
  - `operations.json` — raw classifier output
  - `diff.patch`     — raw unified diff for the range
"""


def _git(args: List[str], cwd: Path) -> str:
    """Run a git command, return stdout (empty string on failure)."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd),
            capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, OSError):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def _narrative(result, ref1: str, ref2: str, cwd: Path,
               *, generated_at: Optional[str] = None) -> str:
    """Build the human-readable context.md body.

    `generated_at` is overridable so tests can pin determinism.
    """
    lines: List[str] = []
    lines.append(f"# Sextant — discuss {ref1}..{ref2}")
    lines.append("")
    ts = generated_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    lines.append(f"- generated: {ts}")
    lines.append(f"- repo: `{cwd}`")
    if result.git_context is not None:
        gc = result.git_context
        if gc.branch:
            lines.append(f"- branch: `{gc.branch}`")
        if gc.pick_state:
            lines.append(f"- pick-state: {gc.pick_state}")
    lines.append("")

    # Op summary
    ops = list(result.operations)
    lines.append(f"## Operations ({len(ops)})")
    lines.append("")
    if not ops:
        lines.append("_No classified operations._")
    else:
        for op in ops:
            kind = getattr(op.kind, "value", op.kind)
            bucket = op.confidence_bucket.value
            tags: List[str] = [bucket]
            if op.evidence.get("pending_llm"):
                tags.append("pending_llm")
            if "llm_refinement" in op.evidence:
                tags.append("llm_refined")
            tag_str = " ".join(f"[{t}]" for t in tags)
            lines.append(
                f"- **{kind}** ({op.confidence:.2f}) {tag_str} — `{op.file}` — {op.summary}"
            )
    lines.append("")

    # Commit messages from git_context
    if result.git_context is not None and result.git_context.commit_messages:
        lines.append("## Commit messages in range")
        lines.append("")
        for m in result.git_context.commit_messages[:20]:
            sha = m.get("sha", "")[:8]
            subj = m.get("subject", "").strip()
            lines.append(f"- `{sha}` — {subj}")
        lines.append("")

    lines.append("## Files touched")
    lines.append("")
    if not result.changes:
        lines.append("_No file changes._")
    else:
        for c in result.changes:
            tag = "renamed" if c.is_renamed else ("new" if c.is_new else ("deleted" if c.is_deleted else "modified"))
            lang = c.language or "-"
            if c.is_renamed:
                lines.append(f"- [{tag}] `{c.path_before}` -> `{c.path_after}` (`{lang}`)")
            else:
                lines.append(f"- [{tag}] `{c.path}` (`{lang}`)")
    lines.append("")
    return "\n".join(lines) + "\n"


@dataclass
class DiscussBundle:
    """The artefact `build_discuss_bundle` returns."""
    bundle_dir: Path
    context_path: Path
    operations_path: Path
    diff_path: Path
    prompt_path: Path
    session_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_dir": str(self.bundle_dir),
            "context_path": str(self.context_path),
            "operations_path": str(self.operations_path),
            "diff_path": str(self.diff_path),
            "prompt_path": str(self.prompt_path),
            "session_id": self.session_id,
        }


def build_discuss_bundle(result, ref1: str, ref2: str,
                         *, cwd: Optional[Path] = None,
                         seed_prompt: Optional[str] = None,
                         generated_at: Optional[str] = None) -> DiscussBundle:
    """Materialise the four bundle files under
    ``.sextant/conversations/<session-id>/``. Returns a DiscussBundle
    handle.

    Determinism: same (cwd, ref1, ref2, result, generated_at) ->
    byte-identical `context.md`, `operations.json`, `diff.patch`,
    `prompt.md`. Tests pin `generated_at` to assert this.
    """
    cwd = (cwd or Path.cwd()).resolve()
    sid = _session_id(cwd, ref1, ref2)
    bundle_dir = (cwd / ".sextant" / "conversations" / sid).resolve()
    bundle_dir.mkdir(parents=True, exist_ok=True)

    context_path = bundle_dir / "context.md"
    operations_path = bundle_dir / "operations.json"
    diff_path = bundle_dir / "diff.patch"
    prompt_path = bundle_dir / "prompt.md"

    # operations.json — full classifier output (round-trippable)
    operations_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True,
                   default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # diff.patch — raw unified diff
    diff_text = _git(["diff", "--no-color", "--find-renames", ref1, ref2], cwd)
    diff_path.write_text(diff_text or "", encoding="utf-8")

    # context.md — narrative
    context_path.write_text(
        _narrative(result, ref1, ref2, cwd, generated_at=generated_at),
        encoding="utf-8",
    )

    # prompt.md — agent seed prompt (with relative pointers to siblings)
    seed = seed_prompt or SEED_PROMPT
    rel = str(bundle_dir).replace("\\", "/")
    full_prompt = (
        seed.rstrip()
        + "\n\nBundle directory: " + rel
        + "\n\nRead `context.md` and `operations.json` from that directory before"
        + " responding. The user will steer the conversation from there.\n"
    )
    prompt_path.write_text(full_prompt, encoding="utf-8")

    return DiscussBundle(
        bundle_dir=bundle_dir,
        context_path=context_path,
        operations_path=operations_path,
        diff_path=diff_path,
        prompt_path=prompt_path,
        session_id=sid,
    )


# ---------------------------------------------------------------------------
# top-level: build bundle + dispatch runner
# ---------------------------------------------------------------------------


def discuss(ref1: str, ref2: str,
            *, cwd: Optional[Path] = None,
            agent: Optional[str] = None,
            files: Optional[List[str]] = None,
            invoker=None,
            detector=None,
            classify=None,
            generated_at: Optional[str] = None) -> Dict[str, Any]:
    """Produce a discuss bundle for `ref1..ref2` and trigger the runner.

    Returns a dict with `bundle` (DiscussBundle.to_dict()) and `runner`
    (RunnerResult.to_dict() or None).

    `agent` accepts any of `RUNNER_CHOICES + PSEUDO_RUNNERS`:
        claude, codex, opencode, stdout, mock, clipboard
    When None, falls back to detect_runner() (env-var / PATH probe).
    `stdout` writes the bundle prompt to stdout and skips the agent.
    """
    from sextant.llm.runner import detect_runner as _detect, invoke_runner as _invoke
    from sextant.git_context import collect as collect_ctx

    cwd = (cwd or Path.cwd()).resolve()
    detector = detector or _detect
    invoker = invoker or _invoke

    if classify is None:
        from sextant.tree_delta import classify_diff as _classify
        classify = _classify

    git_ctx = collect_ctx(cwd, ref1=ref1, ref2=ref2)
    result = classify(ref1, ref2, cwd=cwd, files=files, git_ctx=git_ctx)
    bundle = build_discuss_bundle(result, ref1, ref2, cwd=cwd,
                                  generated_at=generated_at)

    chosen = detector(agent) if agent else detector()
    runner_payload: Optional[Dict[str, Any]] = None
    if agent == "stdout" or chosen == "stdout":
        sys.stdout.write(bundle.prompt_path.read_text(encoding="utf-8"))
        runner_payload = {
            "runner": "stdout", "invoked": False, "exit_code": 0,
            "prompt_path": str(bundle.prompt_path),
        }
    elif chosen is None:
        # No agent on PATH and no explicit fallback — try clipboard so
        # the user can paste into whichever agent they actually use.
        from sextant.llm.runner import copy_to_clipboard
        prompt_text = bundle.prompt_path.read_text(encoding="utf-8")
        ok = copy_to_clipboard(prompt_text)
        runner_payload = {
            "runner": None,
            "fallback": "clipboard" if ok else None,
            "invoked": False,
            "exit_code": 0 if ok else 1,
            "prompt_path": str(bundle.prompt_path),
            "error": None if ok else
                "no agent detected and no clipboard tool found "
                "(install claude/codex/opencode, or xsel/pbcopy/clip.exe)",
        }
    else:
        prompt_text = bundle.prompt_path.read_text(encoding="utf-8")
        result_obj = invoker(chosen, prompt_text,
                             prompt_path=bundle.prompt_path,
                             expect_json=False)
        runner_payload = result_obj.to_dict()

    return {"bundle": bundle.to_dict(), "runner": runner_payload}
