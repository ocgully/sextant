# python-extract-function

Validation block lifted out of `submit_order` into a new helper
`validate_order`. The original function shrinks; the new function
has a body identical to the lifted block.

Expected: `extract-function` operation. May co-emit other ops as the
structural shape changes (e.g. add-method); the snapshot pins
current behavior.
