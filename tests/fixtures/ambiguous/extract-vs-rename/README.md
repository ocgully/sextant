# extract-vs-rename

A new function `validate` appears alongside the original
`submit_order` (which now calls it). Naively this could be read as
"rename submit_order to validate" because submit_order's body
shrinks dramatically.

Expected: extract-function should win — see decision-rationale.md.
