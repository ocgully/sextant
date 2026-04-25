# python-reformat

Whitespace + spacing normalisation only — token sequence
(identifiers, literals) is identical before/after.

Expected: `reformat` operation, high confidence. Should NOT emit
rename/edit ops since no token changed.
