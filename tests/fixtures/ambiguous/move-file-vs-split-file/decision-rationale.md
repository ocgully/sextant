# Why move-file should NOT fire here

move-file requires near-identical body content between
before-path and after-path. Here, neither alpha.py nor beta.py
has a body matching the original lib.py — each contains only HALF
of it. The move-file similarity check (>0.9 confidence) correctly
declines.

Sextant does not yet ship a `split-file` classifier (it's listed
in OperationKind but no detector emits it). Result: lib.py shows
up as a deletion (no after-body), and alpha.py + beta.py show up
as additions, all categorised as `plain-edit`.

**Pin rationale:** when a `split-file` classifier lands, this
fixture's snapshot will fail — that failure tells you the new
classifier is firing on the right shape.
