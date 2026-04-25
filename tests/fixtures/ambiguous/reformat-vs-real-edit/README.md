# reformat-vs-real-edit

Whitespace was normalised AND a `+ 1` was added. Reformat must NOT
fire because the token sequence changed.

Expected: NOT `reformat`; should be `plain-edit` or `change-signature`
depending on which classifier picks it up. See decision-rationale.md.
