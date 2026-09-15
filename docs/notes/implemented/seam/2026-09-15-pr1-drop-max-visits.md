# Agent Note: Drop max_visits graph-topology invariant — PR1

Status: implemented

## Problem

`max_visits` is a per-node hard ceiling on `PlanNode` re-entry in the v2 subgraph driver. 75 of 80 yaml declarations are decorative (`= 1`); the 5 non-`1` values (`think.reason=8`, `think.gate=8`, `think.main=2`, `act.main=2`, `think.reason.complete=3`) terminate legitimate tool-round loops before the think subgraph has converged. `run_cc39610072bf` burned through the counter while think was still producing fresh input — the counter observes visit count, not progress.

## Decision

Delete `max_visits` from the v2 driver surface in PR1: `PlanNode`, `PhaseNode`, `PlanNodeSpec`, `PlanTraversal.visit`, `PlanInterpreter.run`, `metadata_of`, `lift_graph_spec`, `lift_executable_plan`, `plan_sdk`, the three boot-validation checks (`max_visits_bounds`, `max_visits_vs_scc`, `self_loop`), all 80 yaml declarations, and the ~30 test fixtures that reference the field.

## Alternatives considered

- **Keep `max_visits`, add `MultiToolLoopBreaker` to default gate chain** — rejected: PR2's wire-shape fix removes the cycle the breaker was guarding, so the counter becomes pure overhead (75 decorative + 5 harmful declarations).
- **Replace with LangGraph-style `recursion_limit`** — rejected: `recursion_limit` caps super-steps globally at the executor layer, a different shape from per-node visit count; no current use case demands it.
- **Increase the `max_visits` values** — rejected: a higher counter only delays the same bug (`run_cc39610072bf`); the right termination signal is `Decision(action_type=respond)` plus `AgentState.budget`, not a ceiling on the wrong counter.
- **Do nothing (baseline)** — rejected: leaves the 75 decorative + 5 harmful declarations in place and forces every reader of `PlanNode` to learn a counter semantics that does not contribute to termination.

## Consequences (verified via PR1 commit)

After PR1:

- Termination signals are `Decision(action_type=respond)`, `should_terminate` from `act.observe`, and `AgentState.budget` (`max_steps`, `max_wall_clock_seconds`, `max_tokens`).
- `MultiToolLoopBreaker` stays available for opt-in runtimes; PR2 removes the default-gate-chain wiring.
- The `self_loop` check is replaced in PR2 by per-node `terminal_predicate`, which lets self-loops declare their own exit condition.

## Cross-references

- ADR: `docs/adr/0225-drop-max-visits-graph-invariant.md`
- Spec: `docs/superpowers/specs/2026-09-15-session-write-path-design.md` §F
- Plan: `docs/superpowers/plans/2026-09-15-pr1-remove-max-visits.md`
