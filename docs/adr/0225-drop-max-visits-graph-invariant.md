# ADR-0225: Drop `max_visits` graph-topology invariant

## Status

Proposed → Implemented in the same PR (PR1 of the session-write-path redesign)

## Context

`max_visits` is a per-node counter that the v2 subgraph driver enforces as a hard ceiling on how many times a `PlanNode` may be visited during one run. It is declared on `PlanNode`, `PhaseNode`, and `PlanNodeSpec`; it is the kernel-side shape behind the `max_visits:` yaml key in `bundles/**/*.yaml`; it is the trigger for two boot-validation checks (`max_visits_bounds`, `max_visits_vs_scc`) and for the `self_loop` check that guards against infinite cycles.

A census of the 80 yaml lines carrying `max_visits:` shows that 75 of them are decorative — the value is `1`, and a node with `entry=True` is visited exactly once by construction. The 5 non-`1` values (`think.reason=8`, `think.gate=8`, `think.main=2`, `act.main=2`, `think.reason.complete=3`) prevent legitimate tool-round loops: `think.main=2`, for example, terminates a run after the second tool call regardless of whether the model has converged. The original failure run `run_cc39610072bf` burned through `max_visits` budget while the think subgraph was still producing fresh input, because the counter is a passive ceiling that does not observe whether progress is being made.

Cross-checked against OpenAI Agents SDK, Anthropic Claude Agent SDK, LangGraph, and DSH: none expose an analogous per-node hard counter. LangGraph's `recursion_limit=1000` is a graph-executor ceiling on super-steps globally, not a per-node visit counter; it is a different shape and a different layer. LCA already carries `MultiToolLoopBreaker` for runtimes that need fingerprint-based loop detection; with the wire-shape fix landing in PR2 (persist-before-execute + graph-node-ification), the orphan cycle that originally motivated fingerprint detection never starts.

`max_visits` therefore provides negligible protective value (the 75 decorative declarations do nothing) while imposing a real cost (the 5 non-`1` declarations kill correct behavior). AGENTS.md §3 C1 classifies this as a change to core loop-termination semantics, which mandates an ADR before code.

## Decision

Delete `max_visits` from the v2 graph driver surface in PR1 (subtraction-only). Specifically:

- Remove the `max_visits` field and its `_max_visits_positive` validator from `lca.contracts.protocols.graph.plan.PlanNode`.
- Remove the `max_visits` kwarg from `lca.framework.graph.traversal.PlanTraversal.visit`; drop the terminal-flip branch that promotes a node to terminal when its visit count exceeds the budget.
- Remove the over-budget branch at `lca.framework.graph.interpreter.PlanInterpreter.run` lines 127–149; drop the `max_visits=node.max_visits` argument from the `traversal.visit` call.
- Remove `max_visits` from `metadata_of` in `lca.framework.graph.observation.py`; drop the `("max_visits", value)` tuple emission at line 188.
- Drop both reads at `lca.framework.graph.lifter.py` lines 133 and 219 (`lift_graph_spec`, `lift_executable_plan`).
- Drop the `max_visits` kwarg and serializer branch in `lca.framework.graph.plan_sdk.py` lines 215, 336, 485.
- Drop `PhaseNode.max_visits` at `lca/contracts/protocols/declarative/declarative_1/declarative_graph.py` line 83; rephrase the PG-001 check at lines 93–95 to an id-only uniqueness check.
- **Keep** `PlanNodeSpec.max_visits` at `lca/contracts/observability/observation/m1_blueprint/__init__.py` line 23. This is a separate observability-snapshot namespace (`PlanNodeSpec` is the compile-time projection emitted by `lca/plugins/observation/lifecycle/plan_compile/plugin.py:80`); the field stays for the blueprint-trajectory-differ plugin to consume. The runtime `PlanNode.max_visits` field is what this ADR deletes.
- Drop the projections at `lca/harness/declarative/compile/subgraph_resolver.py` lines 200, 236–242 and the field at `lca/harness/profile/plan/explain.py` line 43.
- Drop the `max_visits` kwarg from the resume-path `traversal.visit` call at `lca/loop/driver.py` line 164.
- Drop the `max=` label from `lca/infrastructure/cli/commands/profile/declarative_graph.py` line 28 and the `"max_visits"` key from `lca/infrastructure/cli/commands/profile/declarative.py` line 280.
- Drop the `max_visits` column from `scripts/lca-inspect-plan.py` lines 38, 46.
- Delete the boot-validation files `lca_kernel/boot/plan_validation/checks/max_visits_bounds.py`, `max_visits_vs_scc.py`, and `self_loop.py`; remove their imports and registrations from `lca_kernel/boot/plan_validation/__init__.py`.
- Delete `tests/lca_kernel/boot/test_max_visits_bounds_check.py` and `tests/lca_kernel/boot/test_max_visits_vs_scc_check.py`.
- Delete the 80 `max_visits:` lines across 31 yaml files in `bundles/**/*.yaml`.
- Drop `max_visits=N` kwargs and assertions from the ~30 test fixtures enumerated in PR1 Task 4.
- Delete the obsolete tests in `tests/unit/framework/graph/test_kernel.py` (`test_max_visits_enforced`, `test_run_uses_max_visits`, `test_run_terminates_cleanly_on_max_visits_exceeded`, the `_Node` fixture) and `tests/unit/contracts/graph/test_protocols.py` (`test_max_visits_must_be_positive`, the `max_visits==1` default-value assertion).

## Consequences

After PR1 lands, the only termination signals in the v2 driver are:

- `Decision(action_type=respond)` from the think subgraph (semantic stop signal).
- `should_terminate` from `act.observe` (success/abort flip).
- `AgentState.budget` (`max_steps`, `max_wall_clock_seconds`, `max_tokens`) — run-level ceilings, not per-node counters.

`MultiToolLoopBreaker` remains available for runtimes that opt into fingerprint-based detection; with PR2's wire-shape fix it is no longer in the default gate chain. The `self_loop` boot-validation check is replaced in PR2 by per-node `terminal_predicate`, which lets self-looping nodes declare their own exit condition rather than being forbidden outright.

This PR is subtraction-only: no behavior is added, no run that was previously terminating continues running, and no run that was previously running now terminates spuriously. The behavior-change surface is bounded by the 5 non-`1` yaml values, and each of those values was previously masking a real bug (`run_cc39610072bf`) where the counter fired before the think subgraph had a chance to converge.

Per AGENTS.md §4 ("删除前必须有 owner + delete-when condition"): the owner is PR1 itself; the delete-when clause for every deletion above is "this PR". No shim is introduced, no parallel mechanism is added, and no extension points are created for runtimes that might want to re-introduce the field — re-introduction would require a fresh ADR.

## Alternatives considered

- **Keep `max_visits` and add `MultiToolLoopBreaker` to the default gate chain.** Rejected: with the PR2 wire-shape fix the orphan cycle that originally motivated fingerprint detection never starts, so the per-node counter becomes pure overhead — 75 decorative declarations that do nothing plus 5 declarations that suppress correct behavior. Adding a second loop-termination mechanism on top doubles the surface area (two termination signals, two boot checks, two failure modes) without solving any problem PR2 does not already solve.
- **Replace `max_visits` with a LangGraph-style `recursion_limit`.** Rejected: `recursion_limit` is a graph-executor ceiling on super-steps globally, not a per-node visit counter; it is a different shape, lives at a different layer, and addresses a different failure mode (graph-level runaway, not per-node re-entry). No current use case demands it; if one emerges, it can be added later as its own ADR without blocking PR1's deletion.
- **Increase the `max_visits` values.** Rejected: the premise ("an outer counter prevents runaway") is wrong — the counter fires before think has converged (`run_cc39610072bf`), so a higher counter only delays the same bug. The cure is the right termination signal (`Decision(action_type=respond)` + `AgentState.budget`), not a higher ceiling on the wrong one.
- **Do nothing (baseline).** Rejected: leaving the field in place preserves the 5 buggy non-`1` declarations that mask `run_cc39610072bf`-class failures, keeps the 75 decorative declarations as maintenance debt, and forces every reader of `PlanNode` to learn a counter semantics that does not contribute to termination.
