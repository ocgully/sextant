# concurrent-rename — `user_id` -> two different new names

Both branches renamed the same identifier (`user_id`) to different
targets. The classifier should flag CONCURRENT_RENAME with high
confidence (since base is provided), and the suggestion list must
include both unify-to-X options.
