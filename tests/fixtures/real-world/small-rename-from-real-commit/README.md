# small-rename-from-real-commit

A 1-symbol rename of the `detect_lang` -> `detect_language` helper,
patterned after a real Sextant commit during phase 1A. The shape
(small surface area, single function, in-file callers updated) is
the most common refactor in any codebase.

Expected: `rename-symbol` operation, high confidence.
Source: synthetic but representative of /c/git/sextant commits.
