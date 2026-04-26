# llm/ — placeholder for phase 1E

The Haiku residual classifier lands here in phase 1E of HW-0056 — it
runs only on low-confidence operations the rule-based pipeline
couldn't claim, and only when the user opts in with `--llm`. The
agent-session hand-off pattern from §6.5 lives alongside it.

See `patterns/drafts/diffsextant-plan.md` §4.1 step 4 and §6.5 in
AgentFactory for the full design. Phase 1A is fully deterministic and
has no LLM dependency.
