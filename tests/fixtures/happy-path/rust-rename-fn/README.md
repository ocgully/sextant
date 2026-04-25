# rust-rename-fn

Rename a pub fn from `get_user_id` to `get_account_id`. Rust
tree-sitter `function_item` drives the match.

Expected: `rename-symbol` operation, high confidence.
