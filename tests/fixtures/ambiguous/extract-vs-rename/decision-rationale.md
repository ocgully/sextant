# Why extract-function should win, not rename

Sextant's rename detector requires body-similarity above a
threshold (~0.6 Jaccard on normalised tokens). After the
"rename", submit_order's body is `validate(order); return
save(order)` — bodies are NOT similar to the before, so the rename
heuristic correctly declines.

The extract-function classifier instead fires because:
  - A new function with NO previous match was added
  - Its body matches a contiguous block of the source
  - The original function gained a call-site to the new one

**Pin rationale:** extract-function is the correct classification.
Rename should NOT fire. If it does, that's drift — likely a
similarity-threshold regression.
