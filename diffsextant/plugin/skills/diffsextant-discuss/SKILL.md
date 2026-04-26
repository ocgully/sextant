---
name: diffsextant-discuss
description: |
  Discuss a DiffSextant-classified diff with the user. Loads the
  conversation bundle from `.diffsextant/conversations/<session-id>/`
  (built by `diffsextant discuss` or the GUI's "Discuss this diff"
  button) and helps the user reason about the operations DiffSextant
  detected — surface high-impact / low-confidence ops, confirm or
  correct residual classifications, suggest follow-ups, and answer
  questions about intent + risk. No API key needed; this skill runs
  inside the user's existing Claude Code session.
when_to_use: |
  Activate when the user asks to "discuss this diff" / "review what
  DiffSextant found" / "look at the operations bundle" — typically
  after they've run `diffsextant discuss <ref1> <ref2>` or clicked the
  "Discuss this diff" button in the GUI.

  Also activate when the user pastes a path like
  `.diffsextant/conversations/<id>/context.md` or
  `.diffsextant/conversations/<id>/operations.json`. Legacy
  `.sextant/conversations/...` paths from pre-rename projects also
  count.
inputs:
  - bundle_dir (optional): the discussion bundle directory. When
    omitted, look for the most recent `.diffsextant/conversations/*/`
    (or legacy `.sextant/conversations/*/`) under the cwd.
outputs:
  - A structured conversation that opens with a 3-5 bullet summary of
    the most impactful operations + any low-confidence residuals worth
    a closer look, then takes the user's lead.
---

# diffsextant-discuss

You are reviewing a DiffSextant-classified diff with the user.
DiffSextant has already done the deterministic work — the bundle on
disk lists every classified change with confidence + evidence. Your
job is to discuss it: surface implications, spot missed intent, and
answer follow-ups.

## Bundle layout

Under `.diffsextant/conversations/<session-id>/` (or the legacy
`.sextant/conversations/<session-id>/` for pre-rename projects):

  - `context.md`     — human-readable narrative (operations list,
                       commit messages in range, files touched)
  - `operations.json` — raw classifier output (round-trippable)
  - `diff.patch`     — raw unified diff for the range
  - `prompt.md`      — the seed prompt that triggered this skill

## Your behaviour

1. **Read the bundle first.** Open `context.md` and `operations.json`.
   Don't ask the user to paste content — it's all on disk.

2. **Open with a tight summary.** 3-5 bullets max. Lead with:
   - the highest-impact operation(s) (high-confidence, public-API
     impact, large blast radius)
   - any low-confidence residuals tagged `pending_llm` or
     `llm_refined` that the user might want to re-classify
   - any anti-patterns DiffSextant flagged (god-class-forming,
     shotgun-surgery, etc.)

3. **Cite paths verbatim** with backticks. Don't paraphrase
   filenames.

4. **Don't mutate the bundle.** This skill is read + advise. Mutations
   go through the DiffSextant CLI (`diffsextant discuss --agent ...`,
   `diffsextant diff ... --llm`).

5. **Respect the deterministic core.** If the user disagrees with a
   high/medium classification, treat it as a request to file a
   DiffSextant fixture, NOT as a request to override DiffSextant's
   output. Low-confidence residuals (`pending_llm`) are fair game to
   refine.

6. **Lead with technical accuracy over prose density.** DiffSextant's
   audience is engineers reviewing real diffs.

## Installation

Manual until `flotilla install diffsextant` lands:

```bash
mkdir -p ~/.claude/skills
cp -r diffsextant/plugin/skills/diffsextant-discuss ~/.claude/skills/
```

A future `flotilla install diffsextant` will wire this automatically.
