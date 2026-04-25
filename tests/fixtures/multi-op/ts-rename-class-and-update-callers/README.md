# ts-rename-class-and-update-callers

Class rename touches two files: the definition site and the
importing caller. Cross-file consistency is exercised here.

Expected: at least one `rename-symbol` (in user.ts), and the caller
file produces a rename or plain-edit per Sextant's per-file
classifier loop.
