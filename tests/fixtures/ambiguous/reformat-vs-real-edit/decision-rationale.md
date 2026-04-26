# Why reformat must NOT fire here

The reformat detector (diffsextant.ops.reformat.ReformatClassifier)
requires the token sequence (identifiers + literals + numbers) to
be IDENTICAL before/after. Adding `+ 1` introduces a new numeric
literal `1`, breaking that invariant.

**Pin rationale:** This fixture protects against a class of
regression where a relaxed reformat detector starts emitting
`reformat` for diffs that contain real semantic changes. Such a
regression would be high-impact: reformat ops are suppressed by
most consumers, so a misclassified semantic change becomes
invisible.

Expected current output: `plain-edit` (no other classifier
recognises the shape).
