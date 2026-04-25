# python-rename-function

Rename a Python function from `get_user_id` -> `get_account_id`. The
function body is unchanged; only the defining identifier and its
in-file call sites flip.

Expected: `rename-symbol` operation with high confidence (> 0.9).
Commit-message keyword "rename" provides a small confidence prior.
