# identical-no-change

Before and after files are byte-identical. The diff is empty.

Expected: zero operations. The driver must NOT emit a plain-edit
placeholder for unchanged files.
