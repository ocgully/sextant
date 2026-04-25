# comment-only-vs-docstring-only

Only the function docstring changed. Both `comment-only` and
`docstring-only` classifiers could plausibly fire.

Expected: `docstring-only` (specific) wins; `comment-only` may also
fire if the underlying detector treats triple-quoted strings as
comments. See decision-rationale.md.
