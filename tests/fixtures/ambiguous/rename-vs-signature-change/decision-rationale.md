# Why this fixture's expected output is what it is

When name AND signature both change, Sextant currently emits
BOTH a `rename-symbol` and a `change-signature` op (two ops). The
rename detector is structural-position-based (same function order,
different name) so it still fires. The change-signature detector
picks up the new parameter independently.

**Pin rationale:** keeping both ops is the safe default — it
surfaces all the meaningful information. A future "composite"
classifier could collapse them into one `change-signature` (where
rename is incidental), but that requires a heuristic for "is the
rename driven by the signature change?". Until that exists, two
distinct ops give the user / agent the most information.

If the policy changes (collapse to one), this fixture's
expected.json will fail and the failure tells you the rule
changed — which is exactly the point.
