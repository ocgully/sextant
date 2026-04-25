# python-move-file-and-rename-symbol

File moves from `old/lib.py` to `new/lib.py` AND the function is
renamed simultaneously.

Expected: `move-file` (path change with body-similarity high enough)
plus a `rename-symbol`. Confidence on move-file may be lower than a
pure-move because the body diverges.
