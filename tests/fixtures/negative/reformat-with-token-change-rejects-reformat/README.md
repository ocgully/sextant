# reformat-with-token-change-rejects-reformat

The literal change `x` -> `y` in the return statement breaks the
reformat invariant.

Expected: NO `reformat` operation; some other classifier (or
`plain-edit`) should fire instead.
