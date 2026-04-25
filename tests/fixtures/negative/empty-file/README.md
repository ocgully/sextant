# empty-file

File starts empty and gains content. This stresses the classifiers
against zero-length input — none of the AST classifiers should
crash.

Expected: a `plain-edit` for the new content (or `add-method` if
recognised). No exceptions in classifier output (warnings empty).
