# Sextant fixture corpus

Snapshot-based regression tests. Every directory under
`<category>/<name>/` is one fixture: a before/after pair plus a golden
`expected.json` that pins Sextant's classifier output.

## Layout

```
tests/fixtures/
├── happy-path/    clean single-op cases, 5 per supported language
├── multi-op/      interleaved diffs (>= 2 operations expected)
├── ambiguous/     two classifiers could plausibly fire — snapshot pins which wins
├── negative/      NOT-X cases (reformat must NOT fire when tokens changed, etc.)
└── real-world/    sampled from real repos (sextant / agentfactory / hopewell)
```

Each fixture contains:

```
<category>/<name>/
├── before/                  tree of files (before state)
│   └── <file>.<ext>
├── after/                   tree of files (after state)
│   └── <file>.<ext>
├── commit-message.txt       optional — commit message context for git_context
├── expected.json            golden output (normalised)
├── README.md                3-5 lines describing the case
└── decision-rationale.md    ambiguous fixtures only: explains why X wins over Y
```

## How tests run

`tests/test_fixtures.py` discovers every fixture, materialises `before/`
and `after/` as two commits in a tmp git repo, runs Sextant's
programmatic classifier (`classify_diff`), normalises the output (drops
`cwd`-dependent fields and unstable risk signals), and compares to
`expected.json`. Drift fails the test with a unified diff.

## Updating snapshots

After an intentional classifier change:

```bash
# either flag form
pytest tests/test_fixtures.py --update-snapshots

# or env var
SEXTANT_UPDATE_SNAPSHOTS=1 pytest tests/test_fixtures.py
```

This rewrites every fixture's `expected.json` from current output. The
test prints `UPDATED snapshot: <category>/<name>` for each one. Diff the
result, sanity-check it, then commit.

## Adding a new fixture

1. Create `tests/fixtures/<category>/<name>/`
2. Write `before/<file>` and `after/<file>` (keep each < 100 lines)
3. Optionally add `commit-message.txt` for git-context priors
4. Write `README.md` explaining the case (3-5 lines)
5. Run `SEXTANT_UPDATE_SNAPSHOTS=1 pytest tests/test_fixtures.py -k <name>` to
   bootstrap `expected.json`
6. Eyeball `expected.json` and verify it matches your intent
7. For `ambiguous/` fixtures: add `decision-rationale.md` explaining why the
   chosen classifier wins (the meta-test enforces this)

## Why snapshot tests

Sextant has 15+ classifiers that interact via priority + confidence
gating. Per-classifier unit tests (in `test_ops.py`) confirm each
classifier's positive cases. Snapshot tests confirm the **composed**
behavior — what actually comes out the other end of `classify_diff` for
a real diff, including:

- Operation ordering and de-duplication
- The plain-edit fallback when nothing classifies
- Risk enrichment signals
- Cross-file detectors (move-symbol, shotgun-surgery)
- Git-context priors (commit-message keyword bumps)

A snapshot failure is either:
- A regression (likely) — fix the classifier and the fixture stays put
- An intentional behavior change — update snapshots and review the diff

The ambiguous fixtures are the BACKBONE: each one pins which of two
plausible classifiers should fire when both could. Silent reclassification
regressions are the highest-impact failure mode for a tool like Sextant,
and these fixtures catch them.
