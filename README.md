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

**Status**: phase 1A (HW-0056). Classifier + CLI + git-context + risk.
Phases 1B-1E land later (merge driver, web UI, conflict tooling, LLM
residual classifier).

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

## License

Apache-2.0. See `LICENSE`.

Author: Christopher Gulliver (ocgully@users.noreply.github.com).

Part of the navigation-ecosystem tool family: **mercator · hopewell ·
pedia · sextant**.
