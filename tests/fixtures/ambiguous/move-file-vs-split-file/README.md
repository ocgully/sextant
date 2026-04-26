# move-file-vs-split-file

One file split into two. A naive move-file detector could fire
twice (or once with low confidence) because path-pairing is
ambiguous.

Expected: see decision-rationale.md. DiffSextant currently lacks a
split-file classifier, so the diff likely surfaces as 1 deletion +
2 additions = three plain-edit / move-file / add ops.
