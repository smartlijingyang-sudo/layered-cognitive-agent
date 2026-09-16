# ADR-0240 — Node-level emit dispatch whitelist additions

## Status

**Implemented** (2026-09-15). Plan: `.superpowers/sdd/2026-09-15-node-emit-dispatch-wiring/PLAN.md`. Spec (Agent Note, now `implemented/`): [`../notes/implemented/seam/2026-09-15-node-emit-dispatcher-wiring.md`](../notes/implemented/seam/2026-09-15-node-emit-dispatcher-wiring.md). Validation: `tests/framework/graph/test_interpreter_node_emit.py` + `tests/lca_kernel/boot/test_node_event_emission_check.py` 13/13. `NodeEventEmissionCheck` re-enable deferred to follow-up PR.

## Context

BundleGraphSpec v2 (ADR-0217 §3.3.2) declares `emit_on_enter` / `emit_on_exit` per-node config keys. Production yaml already uses 10 EP names across outer-plan, phase-fold, and subgraph boundaries. The dispatcher table `lca/loop/emit/node_emitter.py:_EP_DISPATCH` maps 11 keys today (5 legacy underscore-form + 6 dot-form), but only the 6 dot-form keys have working helpers in `lca/infrastructure/session/emit/cognitive_emit.py`. The remaining 10 EP names that production yaml declares (or will declare once the driver is wired) have no dispatcher entry and no helper, and the driver does not call `emit_for_node` at all.

All 10 EP names are already present in `SPINE_EXECUTION_POINTS` (`lca_kernel/events/payloads/spine.py`) and registered in `_SPINE_EP_TO_CATEGORY` with a matching `spine.yaml` category row. No whitelist constant addition is required — the C11 closure evidence is that the whitelist, category map, and yaml registration all pre-exist. What is missing is the dispatcher-table mapping and the per-EP helper that publishes via `publish_ep_bound`.

C11 invariant (from AGENTS.md §3): every new execution point must satisfy whitelist entry + SpineHandler registration + test + ADR. This ADR satisfies the ADR requirement for the 10 EPs the node dispatch wiring introduces; the whitelist entry, category mapping, yaml registration, handler, and test are the other four legs.

## Decision

The 10 EP names below form the closed set of dispatchable execution points for the node-level emit wiring. Each maps to one `emit_*_for_state` helper in `lca/infrastructure/session/emit/cognitive_emit.py` (created by the implementation task) and one `_EP_DISPATCH` entry in `lca/loop/emit/node_emitter.py`. The driver (`PlanInterpreter.run`, the only `strategy.execute` call site) calls `dispatch_node_emits` at node enter and exit, contained with `contextlib.suppress(Exception)`. Dispatch that lives in one strategy class skips every other binding: `terminal.commit` binds to `terminate`, so `TerminateStrategy` ran it and row 1 below never fired.

The existing underscore-form dispatcher keys (`prompt_assembler_start`, `prompt_assembler_end`, `reasoner_meta`, `reasoner_reason_start`, `reasoner_reason_end`) remain in `_EP_DISPATCH` unchanged — they are private aliases used by `bundles/think_reason.yaml`, not whitelist entries.

### Closed-set EP table

| # | EP name | Producer seam | Helper (Task 3) | Consumer projection | C11 evidence |
|---|---|---|---|---|---|
| 1 | `terminal.commit` | `PlanInterpreter` post-`execute` dispatch on outer-plan `terminal.commit` node exit | `emit_terminal_commit_for_state` | `spine.terminal.commit` category → `*.spine.jsonl` fold to `terminal_outcome` | whitelist: `spine.py:82`; category: `spine.py:259`; yaml: `spine.yaml:740`; test: `tests/framework/graph/test_interpreter_node_emit.py::test_terminate_binding_fires_declared_emit_on_exit` |
| 2 | `phase.perceive.fold` | `PlanInterpreter` post-`execute` dispatch on perceive phase-graph fold node | `emit_phase_perceive_fold_for_state` | `spine.phase.perceive.fold` category → fold deriver for perceive projection | whitelist: `spine.py:71`; category: `spine.py:255`; yaml: `spine.yaml:701`; test: `tests/framework/graph/test_interpreter_node_emit.py::test_node_executor_binding_still_fires_declared_emits` |
| 3 | `phase.think.fold` | `PlanInterpreter` post-`execute` dispatch on think phase-graph fold node | `emit_phase_think_fold_for_state` | `spine.phase.think.fold` category → fold deriver for think projection | whitelist: `spine.py:72`; category: `spine.py:256`; yaml: `spine.yaml:711`; test: `tests/framework/graph/test_interpreter_node_emit.py::test_node_executor_binding_still_fires_declared_emits` |
| 4 | `phase.reflect.fold` | `PlanInterpreter` post-`execute` dispatch on reflect phase-graph fold node | `emit_phase_reflect_fold_for_state` | `spine.phase.reflect.fold` category → fold deriver for reflect projection | whitelist: `spine.py:75`; category: `spine.py:260`; yaml: `spine.yaml:760`; test: `tests/framework/graph/test_interpreter_node_emit.py::test_node_executor_binding_still_fires_declared_emits` |
| 5 | `phase.remember.fold` | `PlanInterpreter` post-`execute` dispatch on remember phase-graph fold node | `emit_phase_remember_fold_for_state` | `spine.phase.remember.fold` category → fold deriver for memory projection | whitelist: `spine.py:73`; category: `spine.py:257`; yaml: `spine.yaml:722`; test: `tests/framework/graph/test_interpreter_node_emit.py::test_node_executor_binding_still_fires_declared_emits` |
| 6 | `phase.stop.fold` | `PlanInterpreter` post-`execute` dispatch on stop phase-graph fold node (`PhaseName.stop`) | `emit_phase_stop_fold_for_state` | `spine.phase.stop.fold` category → fold deriver for stop projection | whitelist: `spine.py:74`; category: `spine.py:258`; yaml: `spine.yaml:732`; test: `tests/framework/graph/test_interpreter_node_emit.py::test_node_executor_binding_still_fires_declared_emits` |
| 7 | `phase.act.fold.start` | `PlanInterpreter` pre-`execute` dispatch on act phase-graph fold-start node | `emit_phase_act_fold_start_for_state` | `spine.phase.act.fold.start` category → fold deriver for act projection (paired with existing `phase.act.fold.end`) | whitelist: `spine.py:76`; category: `spine.py:261`; yaml: `spine.yaml:771`; test: `tests/framework/graph/test_interpreter_node_emit.py::test_node_executor_binding_still_fires_declared_emits` |
| 8 | `think.gate.end` | `PlanInterpreter` post-`execute` dispatch on `think.gate` node exit (paired with existing `think.gate.start` at line 41) | `emit_think_gate_end_for_state` | `spine.cognition.think.gate.end` category → gate-decided projection | whitelist: `spine.py:42`; category: `spine.py:194`; yaml: `spine.yaml:63`; test: `tests/framework/graph/test_interpreter_node_emit.py::test_node_executor_binding_still_fires_declared_emits` |
| 9 | `phase_graph.subgraph.enter` | `PlanInterpreter` pre-`execute` dispatch on subgraph recursion entry | `emit_phase_graph_subgraph_enter_for_state` | `spine.phase_graph.subgraph.enter` category → graph projection (depth tracking) | whitelist: `spine.py:104`; category: `spine.py:281`; yaml: `spine.yaml:873`; test: `tests/framework/graph/test_interpreter_node_emit.py (no subgraph-binding case yet)` |
| 10 | `phase_graph.subgraph.exit` | `PlanInterpreter` post-`execute` dispatch on subgraph recursion exit | `emit_phase_graph_subgraph_exit_for_state` | `spine.phase_graph.subgraph.exit` category → graph projection (outcome + depth) | whitelist: `spine.py:105`; category: `spine.py:282`; yaml: `spine.yaml:885`; test: `tests/framework/graph/test_interpreter_node_emit.py (no subgraph-binding case yet)` |

C11 coverage gap: the cited tests pin the *dispatch mechanism* (every binding fires its declared list, enter before / exit after `execute`, containment, ordering), not one case per EP row. Rows 2–10 have no EP-specific test, and rows 9–10 have no `subgraph`-binding case at all. Adding them is the outstanding leg of this ADR's C11 claim.

### Helper signature convention

Each new helper follows the existing pattern in `cognitive_emit.py`:

```python
def emit_<ep_name>_for_state(
    state: AgentState,
    *,
    session: object | None = None,
    actor: str = "<phase>",
) -> AppendReceipt | None:
    return publish_ep_bound(
        "<ep.name>",
        {"state_id": state.trace_id},
        state=state,
        session=session,
        actor=actor,
    )
```

Payload fields beyond `state_id` are added only when the yaml declaration or the spine.yaml category row demands them (e.g., `outcome`, `depth`). The helper calls `publish_ep_bound` from `lca/loop/fact_gateway.py`, which resolves the bound Session and fails noisily if none is available.

### Legacy keys

The following `_EP_DISPATCH` keys are **not** affected by this ADR and remain in place:

- `prompt_assembler_start` → `emit_prompt_assembler_start_for_state`
- `prompt_assembler_end` → `emit_prompt_assembler_end_for_state`
- `reasoner_meta` → `None` (special path via `emit_reasoner_meta_for_node`)
- `reasoner_reason_start` → `emit_reasoner_reason_start_for_state`
- `reasoner_reason_end` → `emit_reasoner_reason_end_for_state`

These are private dispatcher aliases consumed by `bundles/think_reason.yaml`. They use underscore-form names that do not appear in `SPINE_EXECUTION_POINTS` as-is; the underlying EP strings (`prompt_assembler.assemble.start`, etc.) are in the whitelist. No rename or removal is proposed.

## Consequences

### Positive

- **C11 closed-set integrity**: each of the 10 new dispatchable EPs has a documented whitelist entry, category mapping, yaml registration, handler, and test path. No EP enters the dispatch table without all four legs.
- **yaml becomes trigger, not documentation**: `emit_on_enter` / `emit_on_exit` values in production yaml start producing spine events once the driver calls `emit_for_node`. The mental model between "declared EP" and "spine event" closes the gap identified in the [spec](../notes/implemented/seam/2026-09-15-node-emit-dispatcher-wiring.md).
- **No whitelist drift**: all 10 EP names pre-exist in `SPINE_EXECUTION_POINTS`. This ADR adds zero new strings to the closed set — it records the mapping from yaml-declared EP ids to their existing whitelist entries.

### Risks

- **Double-emit with imperative `publish_ep_bound` calls**: act executor's existing imperative calls and the new driver-level dispatch will both fire `phase.tool.call.start/end` and friends once wired. The spec identifies this as out of scope for this change; the implementation task must verify that the existing dispatcher entries for `phase.tool.call.start` and `phase.tool.call.end` do not double-fire alongside the executor's direct calls.
- **Validator path fix**: `NodeEventEmissionCheck` reads `node.config["emit_on_enter"]` but yaml stores values at `node.config["config"]["emit_on_enter"]`. The implementation task fixes the path lookup; this ADR does not change validator behavior.

### Out of scope

- Adding new EP names to `SPINE_EXECUTION_POINTS` — all 10 already present.
- Imperative `publish_ep_bound` calls in `cognitive_emit.py`, `tool_journal.py`, `safe_executor.py`, `action_handlers.py`.
- `NodeEventEmissionCheck` re-enable — gated on Tasks 2 and 3 landing with tests.
- Removing or renaming the underscore-form legacy dispatcher keys.

## Related

- [ADR-0230](0230-stop-decision-retirement.md) — `terminal.commit` node replaces `stop.main`; introduced `spine.terminal.commit` EP.
- [ADR-0220](0220-three-tier-graph-and-boundary-typing.md) §3.3 — act-subgraph observation surface; existing `phase.tool.call.*` and `phase.act.fold.end` EPs.
- [ADR-0217](0217-bundle-graph-schema-v2.md) — BundleGraphSpec v2 `emit_on_enter` / `emit_on_exit` schema.
- [ADR-0194](0194-cognitive-loop-architecture-convergence.md) — FactGateway single-entry fact production; six-phase closed set.
- [ADR-0165](0165-execution-point-enforcement.md) — EXECUTION_POINTS whitelist enforcement and I8 closed-set invariant.
- Spec (Agent Note): [`docs/notes/implemented/seam/2026-09-15-node-emit-dispatcher-wiring.md`](../notes/implemented/seam/2026-09-15-node-emit-dispatcher-wiring.md)
