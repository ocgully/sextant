# Sextant

Semantic-operation diff classifier. `git diff` tells you which lines
changed; Sextant tells you what you actually did.

- Renames, extracts, moves, reformats — classified deterministically
  from the AST, not guessed from line deltas.
- Commit-message keywords bias classifier priors (deterministically — same
  diff + same commit message = same output).
- Risk assessment per operation (public-API impact, call-site count,
  test-coverage delta, blame churn, cross-module reach).
- Standalone-first. Mercator and Pedia integrate if installed; absent,
  risk heuristics run locally.
- Text + JSON output. JSON is the agent-consumable surface.
- Installs as a `git diff` driver: matching files route through Sextant
  transparently.

**Status**: phase 1E (HW-0056). Classifier + CLI + git-context + risk +
LLM residual classifier + `sextant discuss` agent-session hand-off.
Phases 1B/1C (git diff-driver wiring, web UI) land alongside.

---

## Install

```bash
pip install sextant[all]          # all 5 language grammars
# or pick individual languages:
pip install sextant[python]
pip install sextant[python,ts,rust]
```

Core has a single runtime dep (`tree-sitter`). Language grammars are
pip extras — install only what your ecosystem needs.

Python 3.10+.

---

## CLI reference (phase 1A subset)

### `sextant diff <ref1> <ref2> [files...]`

Classify the operations between two git refs.

```bash
sextant diff HEAD~1 HEAD
sextant diff main feature/auth --format json
sextant diff abc123 def456 path/to/file.py --risk basic
```

Flags:
- `--format {text|json}` — default `text`
- `--patterns <comma-list>` — include only these operation kinds
- `--risk {off|basic|full}` — risk depth; `basic` uses local heuristics,
  `full` adds Mercator + Pedia if present
- `--show-evidence` — expand evidence dicts in text output

### `sextant explain <commit>`

Same as `sextant diff <commit>^ <commit>`.

### `sextant check <path>`

Runs the malformed-text detector (§3C) + a parse sanity check. Exits
non-zero when signals fire.

```bash
sextant check src/lib.py
sextant check src/broken.py --format json
```

### `sextant cache {clear|stats}`

Manage the `.sextant/cache/` directory.

### `sextant config {get|set|list} [key] [value]`

Read or write `.sextant/config.json`.

### `sextant diff ... --llm`  (phase 1E)

Route LOW-confidence (residual) operations through the user's existing
agent runner (Claude Code, Codex, OpenCode). **No API key is required**
— Sextant invokes the runner as a subprocess; the runner uses its own
auth.

- Operations with `confidence < 0.7` are tagged `pending_llm` (visible
  in JSON output even without `--llm`).
- With `--llm`, each residual gets a focused prompt asking the agent
  to confirm or correct the candidate kind.
- The agent's verdict lands at `evidence.llm_refinement` on the op;
  the deterministic `kind` and `confidence` are NEVER overridden.
- Results are cached at `.sextant/cache/llm/<sha>.json` keyed by op
  shape; same op → same cache hit, regardless of diff range.
- Detection order: explicit `--agent`, then `SEXTANT_AGENT_RUNNER`
  env var (`mock` for CI), then PATH probe (`claude` > `codex` >
  `opencode`).

```bash
sextant diff HEAD~1 HEAD --llm                  # detect runner from PATH
SEXTANT_AGENT_RUNNER=mock sextant diff HEAD~1 HEAD --llm   # tests/CI
```

### `sextant discuss <ref1> <ref2> [--agent ...]`  (phase 1E)

Build a conversation bundle for the diff range and trigger the
runner. The bundle lives at:

```
.sextant/conversations/<session-id>/
    context.md         # human-readable narrative (ops, commits, files)
    operations.json    # raw classifier output (round-trippable)
    diff.patch         # raw `git diff` for the range
    prompt.md          # seed prompt the agent reads first
```

```bash
sextant discuss HEAD~1 HEAD                       # detect runner; invoke
sextant discuss HEAD~1 HEAD --agent claude        # explicit
sextant discuss HEAD~1 HEAD --agent stdout        # print prompt; no agent
sextant discuss HEAD~1 HEAD --agent clipboard     # copy + paste
```

When no runner is detected and no fallback is forced, the prompt is
copied to the OS clipboard via `xsel` / `pbcopy` / Windows `clip.exe`.

A Claude Code skill is shipped under
`sextant/plugin/skills/sextant-discuss/SKILL.md`. Manual install:

```bash
mkdir -p ~/.claude/skills
cp -r sextant/plugin/skills/sextant-discuss ~/.claude/skills/
```

A future `flotilla install sextant` will wire this automatically.

### `sextant register-git-driver [--scope user|repo]`

Install Sextant as a `git diff` driver. Writes `diff.sextant.command`
to git config and adds a `.gitattributes` block for `.py`, `.ts`,
`.tsx`, `.js`, `.rs`, `.go`, `.md`. After this, plain `git diff` on
those files routes through Sextant.

---

## What's classified (phase 1A)

From §3 of the plan: **rename-symbol, extract-function, move-file,
move-symbol, reorder-statements, reformat, comment-only, docstring-only,
lint-fix, invert-condition, add-import, remove-import, reorder-imports,
add-test, remove-test, change-signature, plain-edit (fallback),
malformed (short-circuit).**

From §3B: **strategy-pattern-intro, god-class-forming (anti-pattern),
shotgun-surgery (anti-pattern).**

Remaining §3 / §3B patterns land in phase 1 follow-ups (inline-function,
convert-loop-form, observer, factory, DI, ...). Contributions welcome;
each detector is its own module under `sextant/ops/` or
`sextant/patterns/`.

---

## Architecture

```
  git diff range
        ↓
  [1] collect FileChanges (respect git's --find-renames)
        ↓
  [2] collect git-context (branch, commit msgs, pick-state, adjacent)
        ↓
  [3] per-file: malformed check → classifier pipeline
        ↓
  [4] cross-file: move-symbol + shotgun-surgery
        ↓
  [5] risk enrichment (public-api, call-sites, tests, churn, reach)
        ↓
  [6] render (text | json)
```

Determinism: every classifier is rule-based. Commit-message priors only
bump confidence; they never invent a classification. Same inputs → same
output, always.

---

## Language support

Phase 1A: **Python, TypeScript/JavaScript, Rust, Go, Markdown.**

Other languages degrade to regex-level heuristics (comments, imports,
reformat) plus the plain-edit fallback. Each language grammar is a pip
extra so `pip install sextant[python]` is a viable minimal install.

---

## Integration notes

Sextant has zero hard dependency on other tools in the ecosystem.

- **Mercator** (optional): when `.mercator/` + the `mercator` CLI exist,
  Sextant queries for richer public-API + call-site + system-attribution
  data. Absent, local AST heuristics fill in.
- **Pedia** (optional): when `.pedia/` + the `pedia` CLI exist, Sextant
  surfaces spec-citation impact on classified operations.
- **Hopewell**: not invoked directly; the `explain` / `diff` JSON output
  is intended to be agent-consumable for PR-review automations.

---

## Tests

Two complementary suites:

- **`tests/test_ops.py`** — per-classifier unit tests. Inline before/after
  strings, one assertion per classifier branch.
- **`tests/test_fixtures.py`** — fixture-based snapshot tests. Each
  fixture under `tests/fixtures/<category>/<name>/` ships before/ +
  after/ trees plus a golden `expected.json`. The runner materialises
  the fixture as two commits in a tmp git repo, runs `classify_diff`,
  and compares to the snapshot. See `tests/fixtures/README.md` for the
  full structure and how to add new fixtures.

Update snapshots after an intentional classifier change:

```bash
SEXTANT_UPDATE_SNAPSHOTS=1 pytest tests/test_fixtures.py
# or:  pytest tests/test_fixtures.py --update-snapshots
```

The fixture corpus covers happy-path single-op cases (5 per language for
Python, TypeScript, Rust, Go, Markdown), interleaved multi-op diffs,
ambiguity pins (which of two plausible classifiers wins), negative
cases (NOT-X), and real-world commit shapes.

---

## License

Apache-2.0. See `LICENSE`.

Author: Christopher Gulliver (ocgully@users.noreply.github.com).

Part of the navigation-ecosystem tool family: **mercator · hopewell ·
pedia · sextant**.
