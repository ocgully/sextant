# extract-helper-from-real-commit

Extract-function on a realistic file-tree-walking helper. Patterned
after an AgentFactory `scripts/build-bundle.sh` refactor.

Expected: `extract-function` operation, plus possibly
`add-method`. Realistic refactor noise (whitespace tweaks, slight
structural reshuffle) tests the extract detector against
non-pristine inputs.
