# python-add-import-and-rename

Two clean operations in one diff: a new `import logging` AND a
function rename from `get_user_id` to `get_account_id`. Body of
the renamed function is unchanged.

Expected: `add-import` AND `rename-symbol` (2 ops).
