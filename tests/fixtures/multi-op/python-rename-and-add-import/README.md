# python-rename-and-add-import

Two interleaved operations: function rename `get_user_id` ->
`get_account_id` AND a new `import logging` plus a logging call.

Expected: at least `add-import` and one of
{`rename-symbol`, `change-signature`, `plain-edit`}. Snapshot pins
actual behavior — the rename detector requires body-similarity, and
the added log line may push it to a fallback category.
