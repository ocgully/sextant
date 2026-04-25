# rename-with-body-change-becomes-edit

Function name changed AND the body is materially different.
Body-similarity Jaccard falls below 0.6 — rename detector should
decline.

Expected: NO `rename-symbol` op (or one only if similarity sneaks
past). Likely a `plain-edit` placeholder.
