# rename-vs-signature-change

The function name flipped (foo -> bar) AND the signature gained a
new defaulted parameter (y=0). A naive matcher could emit two ops
(rename + change-signature) or a single composite.

Expected: see decision-rationale.md.
