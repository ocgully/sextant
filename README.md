# diffsextant

> **Renamed from `sextant` (April 2026).** Package, CLI, and on-disk dir
> all migrate from `sextant` / `.sextant/` to `diffsextant` /
> `.diffsextant/`. The legacy `sextant` CLI entry point still installs
> as a deprecation alias (prints a stderr warning, forwards to
> `diffsextant`). The legacy `.sextant/` directory is auto-detected on
> read; migrate in-place with `diffsextant migrate-from-sextant`.
> Alias kept for two minor cycles.

Semantic-operation diff classifier. `git diff` tells you which lines
changed; diffsextant tells you what you actually did.

- Renames, extracts, moves, reformats — classified deterministically
  from the AST, not guessed from line deltas.
- Commit-message keywords bias classifier priors (deterministically — same
  diff + same commit message = same output).
- Risk assessment per operation (public-API impact, call-site count,
  test-coverage delta, blame churn, cross-module reach).
- Standalone-first. Mercator and Pedia integrate if installed; absent,
  risk heuristics run locally.
- Text + JSON output. JSON is the agent-consumable surface.
- Installs as a `git diff` driver: matching files route through
  DiffSextant transparently.

**Status**: phase 1E (HW-0056). Classifier + CLI + git-context + risk +
LLM residual classifier + `diffsextant discuss` agent-session hand-off.
Phases 1B/1C (git diff-driver wiring, web UI) land alongside.

---

## Install

```bash
pip install diffsextant
# legacy: `pip install sextant` will continue to work for two minor
# cycles via the deprecation-shim package on PyPI.
```

```bash
pip install diffsextant[all]          # all 5 language grammars
# or pick individual languages:
pip install diffsextant[python]
pip install diffsextant[python,ts,rust]
```

Core has a single runtime dep (`tree-sitter`). Language grammars are
pip extras — install only what your ecosystem needs.

Python 3.10+.

---

## CLI reference (phase 1A subset)

### `diffsextant diff <ref1> <ref2> [files...]`

Classify the operations between two git refs.

```bash
diffsextant diff HEAD~1 HEAD
diffsextant diff main feature/auth --format json
diffsextant diff abc123 def456 path/to/file.py --risk basic
```

Flags:
- `--format {text|json}` — default `text`
- `--patterns <comma-list>` — include only these operation kinds
- `--risk {off|basic|full}` — risk depth; `basic` uses local heuristics,
  `full` adds Mercator + Pedia if present
- `--show-evidence` — expand evidence dicts in text output

### `diffsextant explain <commit>`

Same as `diffsextant diff <commit>^ <commit>`.

### `diffsextant check <path>`

Runs the malformed-text detector (§3C) + a parse sanity check. Exits
non-zero when signals fire.

```bash
diffsextant check src/lib.py
diffsextant check src/broken.py --format json
```

### `diffsextant cache {clear|stats}`

Manage the `.diffsextant/cache/` directory.

### `diffsextant config {get|set|list} [key] [value]`

Read or write `.diffsextant/config.json`.

### `diffsextant diff ... --llm`  (phase 1E)

Route LOW-confidence (residual) operations through the user's existing
agent runner (Claude Code, Codex, OpenCode). **No API key is required**
— DiffSextant invokes the runner as a subprocess; the runner uses its own
auth.

- Operations with `confidence < 0.7` are tagged `pending_llm` (visible
  in JSON output even without `--llm`).
- With `--llm`, each residual gets a focused prompt asking the agent
  to confirm or correct the candidate kind.
- The agent's verdict lands at `evidence.llm_refinement` on the op;
  the deterministic `kind` and `confidence` are NEVER overridden.
- Results are cached at `.diffsextant/cache/llm/<sha>.json` keyed by op
  shape; same op → same cache hit, regardless of diff range.
- Detection order: explicit `--agent`, then `DIFFSEXTANT_AGENT_RUNNER`
  env var (legacy `SEXTANT_AGENT_RUNNER` honoured for one cycle, `mock`
  for CI), then PATH probe (`claude` > `codex` > `opencode`).

```bash
diffsextant diff HEAD~1 HEAD --llm                  # detect runner from PATH
DIFFSEXTANT_AGENT_RUNNER=mock diffsextant diff HEAD~1 HEAD --llm   # tests/CI
```

### `diffsextant discuss <ref1> <ref2> [--agent ...]`  (phase 1E)

Build a conversation bundle for the diff range and trigger the
runner. The bundle lives at:

```
.diffsextant/conversations/<session-id>/
    context.md         # human-readable narrative (ops, commits, files)
    operations.json    # raw classifier output (round-trippable)
    diff.patch         # raw `git diff` for the range
    prompt.md          # seed prompt the agent reads first
```

```bash
diffsextant discuss HEAD~1 HEAD                       # detect runner; invoke
diffsextant discuss HEAD~1 HEAD --agent claude        # explicit
diffsextant discuss HEAD~1 HEAD --agent stdout        # print prompt; no agent
diffsextant discuss HEAD~1 HEAD --agent clipboard     # copy + paste
```

When no runner is detected and no fallback is forced, the prompt is
copied to the OS clipboard via `xsel` / `pbcopy` / Windows `clip.exe`.

A Claude Code skill is shipped under
`diffsextant/plugin/skills/diffsextant-discuss/SKILL.md`. Manual install:

```bash
mkdir -p ~/.claude/skills
cp -r diffsextant/plugin/skills/diffsextant-discuss ~/.claude/skills/
```

A future `flotilla install diffsextant` will wire this automatically.

### `diffsextant register-git-driver [--scope user|repo] [--uninstall]`

Install (or uninstall) DiffSextant as a `git diff` driver. Writes
`diff.sextant.command` to git config and — for repo scope — adds a
sentinel-marked block to `.gitattributes` for `.py`, `.ts`, `.tsx`,
`.js`, `.rs`, `.go`, `.md`. After this, plain `git diff` on those
files routes through DiffSextant.

> The git-config key namespace and the `.gitattributes` sentinel both
> still spell `sextant` so existing repos that registered the driver
> before the rename keep working without re-registration. Only the CLI
> and the package name moved.

`--uninstall` is surgical: it strips only the `sextant:managed` block
and `diff.sextant.*` keys, leaving every other line in
`.gitattributes` (and every other git-config key) untouched.

---

## Use DiffSextant as your default `git diff`

```bash
# 1. install in your project
cd your-project
pip install diffsextant[all]
diffsextant register-git-driver --scope repo
```

This makes two changes:

- writes a `[diff "sextant"]` section to `.git/config`:

      [diff "sextant"]
        command = diffsextant diff --git-driver-mode --format text
        binary = false
        cachetextconv = false

- appends a sentinel-bracketed block to `.gitattributes`:

      # >>> sextant:managed (do not edit) >>>
      *.py   diff=sextant
      *.ts   diff=sextant
      *.tsx  diff=sextant
      *.js   diff=sextant
      *.rs   diff=sextant
      *.go   diff=sextant
      *.md   diff=sextant
      # <<< sextant:managed <<<

```bash
# 2. run git diff as you normally would
git diff lib/foo.py
```

For matching files, git pipes the before/after blobs into
`diffsextant diff --git-driver-mode --format text`, and the operations
you actually performed (rename · extract · reformat · ...) appear
inline instead of raw line deltas.

```bash
# 3. uninstall — surgical, leaves user content intact
diffsextant register-git-driver --scope repo --uninstall
```

Use `--scope user` to install in `~/.gitconfig` instead. User scope
only writes git config — it does NOT touch any `.gitattributes`.
Configure `core.attributesFile` yourself if you want a global
attributes file.

The install is idempotent: re-running it detects the sentinel block
and leaves it alone. To re-install with different patterns, uninstall
first.

### `diffsextant web [--port N] [--open] [--host H]`

Launches the local web UI (Preact + esm.sh, stdlib `http.server` — no
build step, no npm). Three switchable views:

- **Operations** (default) — operations grouped by file, ordered by
  risk; click any op for the detail pane (before/after, risk signals,
  evidence, narrative).
- **Classic-text** — side-by-side OR unified text-diff with a semantic
  overlay: per-line gutter colour by operation kind, hover tooltip,
  fold-by-operation control, sync-scrolling op list.
- **Timeline** — horizontal track of commits across a range; per-commit
  operation breakdown + risk bar; click to drill into the commit.

```bash
cd /path/to/repo
diffsextant web --port 9881 --open
```

The view-mode (and the active commit / range) live in the URL hash, so
deep-links + reloads are stable. Read-only — every mutation still goes
through the CLI. The conflict resolver and AI-conversation hand-off
land in phases 1D + 1E.

Endpoints (all GET, JSON):

- `/api/meta` — project root + version + HEAD + branch
- `/api/diff/current` — classified `HEAD~1..HEAD`
- `/api/diff?ref1=&ref2=` — explicit range
- `/api/explain?commit=<sha>` — single commit
- `/api/timeline?range=<a>..<b>` — per-commit summary stream

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
each detector is its own module under `diffsextant/ops/` or
`diffsextant/patterns/`.

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
extra so `pip install diffsextant[python]` is a viable minimal install.

---

## Integration notes

DiffSextant has zero hard dependency on other tools in the ecosystem.

- **Mercator** (optional): when `.mercator/` + the `mercator` CLI exist,
  DiffSextant queries for richer public-API + call-site +
  system-attribution data. Absent, local AST heuristics fill in.
- **Pedia** (optional): when `.pedia/` + the `pedia` CLI exist,
  DiffSextant surfaces spec-citation impact on classified operations.
- **Hopewell**: not invoked directly; the `explain` / `diff` JSON output
  is intended to be agent-consumable for PR-review automations.

---

## Conflicts (phase 1D)

DiffSextant classifies the *kind* of three-way merge conflict, not just
the fact that one exists. Five concurrent-operation kinds:

| kind                  | when                                                            |
|-----------------------|-----------------------------------------------------------------|
| `concurrent-rename`   | both sides renamed the same identifier to different targets     |
| `concurrent-edit`     | both sides edited overlapping content                           |
| `concurrent-move`     | both sides preserve the same lines but reorder them differently |
| `add-add`             | base was empty (or absent); both sides added content            |
| `modify-delete`       | one side modified the block; the other deleted it               |

### Inspect a conflicted file

```bash
diffsextant conflict path/to/file.py            # text output
diffsextant conflict path/to/file.py --format json
diffsextant conflict path/to/file.py --resolve  # walk regions interactively
```

Per region the inspector shows risk bucket, classified kind, base/ours/
theirs one-liners, intent signals, and a short list of suggested
resolutions (each keyed to a single letter for the `--resolve` walker).

### Install as a git merge driver

```bash
diffsextant register-merge-driver --scope repo   # writes .gitattributes block
diffsextant register-merge-driver --scope user   # ~/.gitconfig (no .gitattributes)
```

> As with the diff driver, the git-config key (`merge.sextant.*`) and
> the `.gitattributes` sentinel still spell `sextant` so pre-rename
> registrations keep working.

When git invokes DiffSextant as a merge driver (`%O %A %B %P`),
DiffSextant classifies the change-set per region and either:

- writes a resolved file and exits 0 (e.g. both sides made the same
  rename), or
- writes the file with conflict markers + a `# sextant:merge-summary`
  block summarising the classified intents, exiting 1 so git keeps the
  file for the human / agent to fix.

The summary block sits above the markers so editors and agents can read
the classifier's view at a glance without re-running the CLI.

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
DIFFSEXTANT_UPDATE_SNAPSHOTS=1 pytest tests/test_fixtures.py
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
pedia · diffsextant**.
