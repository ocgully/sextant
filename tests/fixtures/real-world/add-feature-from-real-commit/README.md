# add-feature-from-real-commit

Adds a new `cmd_resume` function and threads it through the
argparse subparser registration. Models the most common
"add-feature" diff shape: one new function, two existing functions
edited slightly to register it.

Expected: at least an `add-method` or `extract-function` for the
new handler. The argparse-registration block also gets edits.
Realistic noise — multiple structural ops in a single PR.
