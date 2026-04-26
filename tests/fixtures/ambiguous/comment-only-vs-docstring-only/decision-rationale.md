# Which wins: comment-only or docstring-only

DiffSextant has two distinct classifiers — `docstring-only` is
language-specific (Python triple-quoted strings as the FIRST
statement of a function/class/module). `comment-only` is more
general (#-style comments).

**Pin rationale:** `docstring-only` is the correct classification
for this case (the change is inside a docstring). The
comment-only detector should NOT fire because a docstring is not a
`#`-comment. Both could fire under a too-permissive detector — the
snapshot pins the current correct behavior.

Risk attached to docstring-only is lower than comment-only — both
have minimal call-site impact, but documentation quality is the
ONLY semantic effect.
