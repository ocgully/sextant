# move-file-too-divergent-rejects

Both the path AND the body changed dramatically — body-similarity
below the move-file threshold.

Expected: NO `move-file` operation. Could surface as deletion +
addition (two plain-edits) or as some other shape.
