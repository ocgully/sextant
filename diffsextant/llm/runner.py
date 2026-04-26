"""Agent-runner detection + invocation.

DiffSextant's LLM features all flow through the user's existing agent
runner (Claude Code primary; Codex / OpenCode secondary). We never
import the Anthropic SDK and never read ANTHROPIC_API_KEY. The runner
is treated as a black-box subprocess: hand it a prompt, observe its
exit code + stdout, parse JSON if the prompt asked for JSON.

Detection order:
1. Explicit choice from caller (`detect_runner("claude")`).
2. ``DIFFSEXTANT_AGENT_RUNNER`` env var (``mock`` is supported for
   tests/CI). The legacy ``SEXTANT_AGENT_RUNNER`` is honoured as a
   fallback for one deprecation cycle.
3. First runner found on PATH from `RUNNER_CHOICES` (Claude → Codex →
   OpenCode).

If nothing is detected and no fallback is requested, we copy the
prompt to the OS clipboard via `xsel` / `pbcopy` / Windows `clip.exe`
so the user can paste it into whichever agent they actually use.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Order matters: PATH-detection prefers earlier entries.
RUNNER_CHOICES: Tuple[str, ...] = ("claude", "codex", "opencode")

# `stdout` and `mock` are pseudo-runners — they never invoke a
# subprocess, but they are valid `--agent` arguments.
PSEUDO_RUNNERS: Tuple[str, ...] = ("stdout", "mock", "clipboard")

ALL_RUNNERS: Tuple[str, ...] = RUNNER_CHOICES + PSEUDO_RUNNERS


# ---------------------------------------------------------------------------
# result
# ---------------------------------------------------------------------------


@dataclass
class RunnerResult:
    """Outcome of one runner invocation."""
    runner: str                          # "claude" | "codex" | "opencode" | "stdout" | "mock" | "clipboard"
    invoked: bool                        # True when a subprocess actually ran
    fallback: Optional[str] = None       # name of the fallback used (e.g. "clipboard")
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    parsed: Any = None                   # JSON parse of stdout when applicable
    prompt_path: Optional[str] = None    # disk location of the prompt we handed to the runner
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["prompt_path"] = str(self.prompt_path) if self.prompt_path else None
        return d


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------


def detect_runner(preferred: Optional[str] = None,
                  *, env: Optional[Dict[str, str]] = None,
                  path_lookup=None) -> Optional[str]:
    """Return the first viable runner name, or None.

    Resolution order:
      1. Explicit `preferred` argument (callers that already know).
      2. ``DIFFSEXTANT_AGENT_RUNNER`` env var, falling back to the
         legacy ``SEXTANT_AGENT_RUNNER`` for one deprecation cycle.
         (CI / tests use ``mock`` here.)
      3. First entry in `RUNNER_CHOICES` whose binary is on PATH.

    `path_lookup` is `shutil.which` by default; tests pass a stub.
    """
    env = env if env is not None else os.environ
    path_lookup = path_lookup or shutil.which

    if preferred:
        if preferred in PSEUDO_RUNNERS:
            return preferred
        if preferred not in RUNNER_CHOICES:
            return preferred  # caller passes explicit binary path; trust them
        if path_lookup(preferred):
            return preferred
        # Explicit choice not on PATH — return None so the caller can
        # decide whether to fall back to clipboard.
        return None

    env_choice = env.get("DIFFSEXTANT_AGENT_RUNNER") or env.get("SEXTANT_AGENT_RUNNER")
    if env_choice:
        env_choice = env_choice.strip()
        if env_choice in PSEUDO_RUNNERS:
            return env_choice
        if path_lookup(env_choice):
            return env_choice
        # Env asked for an agent that isn't on PATH — treat as no detection.
        return None

    for candidate in RUNNER_CHOICES:
        if path_lookup(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# clipboard fallback
# ---------------------------------------------------------------------------


def _clipboard_command() -> Optional[List[str]]:
    """Return the argv that, when piped stdin, copies to the OS clipboard.

    None when no clipboard tool is detected. We never raise — clipboard
    is a best-effort fallback.
    """
    sysname = platform.system()
    if sysname == "Windows":
        # clip.exe ships with Windows; consume stdin verbatim.
        if shutil.which("clip"):
            return ["clip"]
        return None
    if sysname == "Darwin":
        if shutil.which("pbcopy"):
            return ["pbcopy"]
        return None
    # Linux + BSDs
    if shutil.which("wl-copy"):
        return ["wl-copy"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard"]
    if shutil.which("xsel"):
        return ["xsel", "--clipboard", "--input"]
    return None


def copy_to_clipboard(text: str, *, runner=None) -> bool:
    """Copy `text` to the OS clipboard. Returns True on success.

    `runner` is `subprocess.run` by default; tests inject a stub.
    """
    runner = runner or subprocess.run
    cmd = _clipboard_command()
    if not cmd:
        return False
    try:
        proc = runner(cmd, input=text, text=True, capture_output=True, check=False)
    except (FileNotFoundError, OSError):
        return False
    return getattr(proc, "returncode", 1) == 0


# ---------------------------------------------------------------------------
# invocation
# ---------------------------------------------------------------------------


def _build_argv(runner: str, prompt_path: Path, *,
                expect_json: bool) -> List[str]:
    """Build the argv to invoke `runner`.

    Each runner has a slightly different "give me one prompt + exit"
    flag set. We keep the shapes here, in one place, so the caller
    just hands us a runner name.
    """
    if runner == "claude":
        # `claude --print` runs once, prints the final assistant message,
        # exits non-zero on tool errors. `--input-format text` keeps the
        # protocol simple; JSON output via `--output-format json`.
        argv = ["claude", "--print"]
        if expect_json:
            argv += ["--output-format", "json"]
        argv += ["--input-format", "text", str(prompt_path)]
        return argv
    if runner == "codex":
        argv = ["codex", "exec"]
        if expect_json:
            argv += ["--json"]
        argv += [str(prompt_path)]
        return argv
    if runner == "opencode":
        argv = ["opencode", "run", "--prompt-file", str(prompt_path)]
        if expect_json:
            argv += ["--json"]
        return argv
    # User-provided absolute path or unknown runner — best-effort.
    return [runner, str(prompt_path)]


def invoke_runner(runner: str, prompt: str, *,
                  prompt_path: Optional[Path] = None,
                  expect_json: bool = False,
                  env: Optional[Dict[str, str]] = None,
                  subprocess_runner=None,
                  timeout: Optional[float] = None) -> RunnerResult:
    """Run `runner` against `prompt`. Returns a RunnerResult.

    `prompt_path` is where we'll persist the prompt to disk so the
    runner can read it (most agent CLIs prefer file-input over stdin
    for long prompts; also makes the bundle reproducible). When None,
    we use a per-call temp file.

    `subprocess_runner` and `env` are injection points for tests; in
    production they default to `subprocess.run` and `os.environ`.
    """
    env = env if env is not None else dict(os.environ)
    subprocess_runner = subprocess_runner or subprocess.run

    # ---- pseudo-runners: stdout, mock, clipboard ----

    if runner == "stdout":
        sys.stdout.write(prompt)
        if not prompt.endswith("\n"):
            sys.stdout.write("\n")
        return RunnerResult(runner="stdout", invoked=False, exit_code=0,
                            stdout=prompt,
                            prompt_path=str(prompt_path) if prompt_path else None)

    if runner == "mock":
        # Deterministic stub for tests/CI. The mock "agent" simply echoes
        # back a structured JSON envelope we can round-trip in tests.
        payload = {
            "runner": "mock",
            "prompt_chars": len(prompt),
            "expect_json": expect_json,
            "classification": {
                "kind": "plain-edit",
                "confidence": 0.55,
                "rationale": "mock runner — no real LLM call",
            },
        }
        out = json.dumps(payload, sort_keys=True)
        return RunnerResult(runner="mock", invoked=False, exit_code=0,
                            stdout=out, parsed=payload,
                            prompt_path=str(prompt_path) if prompt_path else None)

    if runner == "clipboard":
        ok = copy_to_clipboard(prompt)
        return RunnerResult(
            runner="clipboard", invoked=False,
            exit_code=0 if ok else 1,
            stdout="",
            error=None if ok else "no clipboard tool detected (xsel / pbcopy / clip.exe)",
            prompt_path=str(prompt_path) if prompt_path else None,
        )

    # ---- real subprocess invocation ----

    # Persist the prompt to disk if the caller didn't.
    if prompt_path is None:
        import tempfile
        td = Path(tempfile.gettempdir()) / "diffsextant-prompts"
        td.mkdir(parents=True, exist_ok=True)
        # Use the prompt's content hash for caching/reuse + dedup.
        import hashlib
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        prompt_path = td / f"prompt-{digest}.md"
        prompt_path.write_text(prompt, encoding="utf-8")
    else:
        prompt_path = Path(prompt_path)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")

    argv = _build_argv(runner, prompt_path, expect_json=expect_json)
    try:
        proc = subprocess_runner(
            argv,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        # Runner disappeared between detect and invoke. Try clipboard fallback.
        ok = copy_to_clipboard(prompt)
        return RunnerResult(
            runner=runner, invoked=False,
            fallback="clipboard" if ok else None,
            exit_code=None,
            error=f"runner not on PATH: {e}",
            prompt_path=str(prompt_path),
        )
    except subprocess.TimeoutExpired as e:
        return RunnerResult(
            runner=runner, invoked=True, exit_code=None,
            error=f"runner timed out after {timeout}s: {e}",
            prompt_path=str(prompt_path),
        )

    stdout = getattr(proc, "stdout", "") or ""
    stderr = getattr(proc, "stderr", "") or ""
    parsed = None
    if expect_json and stdout.strip():
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
    return RunnerResult(
        runner=runner, invoked=True,
        exit_code=getattr(proc, "returncode", None),
        stdout=stdout, stderr=stderr,
        parsed=parsed,
        prompt_path=str(prompt_path),
    )
