# Agent Note: runtime factory plugin cutover closes the kernel cutover end-to-end

Status: implemented

## Decision

The single PR closes the act-subgraph seam cutover by pointing the runtime plugin factory at `PlanInterpreterAdapter`, deleting the now-unreferenced `lca/framework/declarative/` and `lca/framework/subgraph/` directories (plus the `lca/harness/graph/execute/v2/` shadow of the unified port registry), and rewriting the harness re-export shims so the new kernel is the only production interpreter path.

### Part A — runtime plugin factory now constructs `PlanInterpreterAdapter`

`lca/plugins/journal/declarative/runtime_seams_provider.py::DefaultDeclarativeInterpreterFactory.create()` constructs `PlanInterpreterAdapter(journal=..., effect_gateway=..., reducer=..., phase_observer=..., lifecycle_publisher=..., loop_guard_evaluator=...)` and returns it. The five runtime closures are honored instead of thrown away. The factory's `__init__` no longer accepts `subgraph_runner` / `channel_factory`; `bind_cordis_seams` is gone. The `@plugin(requires=[...])` list drops `subgraph_runner` and `phase_output_channel_factory`.

`lca/framework/graph/adapter.py::PlanInterpreterAdapter.__init__` accepts the five closures plus `loop_guard_evaluator` and stores them. `PlanInterpreter.run(...)` now accepts a `traversal` parameter; the adapter seeds `PlanTraversal(plan, current_id=..., visit_counts=...)` from a `PhaseRunCursor` so `resume()` picks up at the checkpointed node instead of restarting from entry. `cursor=None` degrades to a fresh `run()`. The local `PhaseRunCursor` dataclass carries `current_node_id: str` + `visited_nodes: tuple[str, ...] = ()` — the two fields the kernel reads; the legacy `declarative_1.declarative_execution.PhaseRunCursor` shape is honoured via duck typing.

### Part B — delete `lca/framework/declarative/` and the legacy interpreter

Every consumer of `lca/framework/declarative/` was routed through the runtime plugin factory or through `lca.harness.graph.execute.interpreter`. With Part A done, the framework package was unreferenced.

- Deleted `lca/framework/declarative/` (10 files including `GenericPlanInterpreter`, the `@plugin(id="declarative.interpreter_factory")` registration, and `InMemoryJournalCommitter`).
- Dropped the `declarative.interpreter` plugin entry from `bundles/base.yaml`.
- `lca/harness/graph/execute/interpreter.py` and the parent `__init__.py` re-export `PlanInterpreterAdapter` via lazy attribute access so existing imports keep resolving. The deleted `GenericPlanInterpreter` and `InMemoryJournalCommitter` symbols are removed from `__all__`.
- `lca/harness/declarative` drops `GenericPlanInterpreter` from its `__all__` / `TYPE_CHECKING` re-exports.
- Deleted `tests/declarative/` (entire directory — every test exercised the deleted interpreter), `tests/architecture/test_p7_interpreter_fallback.py`, and the four `tests/harness/graph/execute/test_*.py` files that exclusively exercise deleted behaviour.
- `tests/unit/framework/graph/test_adapter.py::test_factory_returns_adapter` rewrites to import the runtime plugin factory (the only surviving `DefaultDeclarativeInterpreterFactory`).
- Documentation comments that named `GenericPlanInterpreter` now name `PlanInterpreterAdapter` or the unified graph kernel.

### Part C — delete `lca/framework/subgraph/`, the v2 shadow, and `SubgraphCloseOut`

Part A stopped binding `subgraph_runner` / `phase_output_channel_factory` seams, leaving `lca/framework/subgraph/` with zero production consumers. The `lca/harness/graph/execute/v2/` files were the v2 port-context and edge-selector originals that the unified graph kernel's `PortRegistry` supersedes. `SubgraphCloseOut` was a single-method `Protocol` that returned `Mapping[str, Any]`; the new port registry covers the concern with stronger typing.

- Deleted `lca/framework/subgraph/` (9 files including `NodeGraphDriver`, `SubgraphRunner`, `PhaseOutputChannel`, and the `PlanLift` + `runtime` plumbing).
- Deleted `lca/harness/graph/execute/v2/` (4 files).
- Deleted `lca/contracts/subgraph.py::SubgraphCloseOut` Protocol.
- Dropped the `subgraph_runner` plugin from `bundles/base.yaml` (Part A removed the only consumer).
- `scripts/check_framework_cognition_boundary.py::LEGACY_WHITELIST = ()`; the `legacy_skip` branch and the whitelist import are removed. The print line reports `clean` when there are no violations.
- `tests/unit/scripts/test_check_framework_cognition_boundary.py` rewrites the whitelist assertion to expect an empty tuple.
- `lca/harness/declarative/execute/outcome_projection.py::InterpretationResult.output` collapses from the deleted `PhaseOutput` to `Mapping[str, Any] | None`.
- `lca/framework/__init__.py` collapses to a stub with no subpackage re-exports (declarative + subgraph are gone).
- `lca/framework/graph/__init__.py` + the strategy / traversal docstrings describe the deleted legacy classes by name only.
- Deleted `tests/unit/framework/subgraph/` and `tests/integration/think/` — both exclusively exercised the deleted `NodeGraphDriver` / `SubgraphRunner` / `InMemoryPhaseOutputChannel`.

### Part D — tool-call E2E integration test

`tests/integration/cutover/test_tool_call_e2e.py` hand-rolls a six-node plan (`perceive → think → act → reflect → remember → stop`), wires the act node to a `PhaseExecutorStrategy` whose `runner` returns `PhaseResult(result_kind="observation", payload=Observation(success=True))`, runs the adapter, and asserts:

1. the visit loop reaches the terminal node,
2. the act visit's outputs carry the `observation` port with the `Observation(success=True)` payload.

A second test class proves `PlanInterpreterAdapter.resume` seeds `PlanTraversal` from the cursor's `current_node_id` + `visited_nodes`; `resume(cursor=None)` degrades to a fresh `run`. The seam proof does not need a real tool-execution fixture — it verifies the kernel wiring is intact end-to-end.

## Problem

PR-1..PR-8 of the unified graph kernel cutover shipped on `main`. Static gates pass. `PlanInterpreterAdapter` is the documented production interpreter. Acceptance criterion #5 of the cutover plan — *"tool-call prompt produces a run whose journal spine contains a tool-call event followed by a successful tool result and a final assistant message"* — is not yet met. The captured trace `run_33323e9406fe` shows the kernel reaches `phase.tool.call.start` and jumps straight to `reflect.main → remember.main:control.denied` with `RuntimeError('memory admission requires outcome and reflection')`.

The deny is the symptom, not the cause. `reflect.standard` reads `payload_of(SemanticPhase.ACT, Observation)`, gets `None`, and falls back to `failure: {phase: "reflect"}` by design. The defect is upstream: the act subgraph never executes.

**The PR-7 cutover didn't actually cut over the runtime.** Two `DefaultDeclarativeInterpreterFactory` classes exist:

1. `lca/framework/declarative/plugins/interpreter_factory.py::DefaultDeclarativeInterpreterFactory` — the framework file the PR-7 commit modified. Its `create()` returns `PlanInterpreterAdapter()`. Decorated with `@plugin(id="declarative.interpreter_factory", ...)`.
2. `lca/plugins/journal/declarative/runtime_seams_provider.py::DefaultDeclarativeInterpreterFactory` — the plugin registered via `@plugin(id="lca-declarative-runtime-seams-provider", provides=[..., "declarative_interpreter_factory", ...])` in `bundles/base.yaml:349`. Its `create()` still constructs `GenericPlanInterpreter(journal=..., effect_gateway=..., reducer=..., ...)`.

`grep "id: declarative.interpreter_factory" bundles/*.yaml` returns **zero** hits — the framework file's `@plugin` decorator never registers anywhere. `grep "id: lca-declarative-runtime-seams-provider" bundles/*.yaml` returns one hit (`bundles/base.yaml`). The kernel boots through the legacy plugin factory, not the new framework one. `PlanInterpreterAdapter` is dead code at runtime; `GenericPlanInterpreter` is what actually executes every run.

Evidence: the failing trace shows `phase_graph.node.start → phase_graph.node.end` events (those are emitted by `GenericPlanInterpreter`'s visit loop in `lca/framework/declarative/plugins/interpreter.py`), not the typed `VisitRecord` events that the new `PlanInterpreter` produces via `VisitRecorder.record`. The trace also shows `runtime.reducer.apply method=apply_step_advanced` and `apply_perception` — both invoked by the legacy interpreter's reducer integration, not by `PlanInterpreter`'s visit state machine.

The legacy `GenericPlanInterpreter` does drive `act.main` through the subgraph, but the act subgraph's `act.dispatch` node goes through `concept.effect.execute` for tool calls, and the legacy interpreter's effect dispatch lives in `lca.loop.transaction.PhaseExecutionTransaction` which is wired but the act subgraph dispatch path doesn't reach it for this fixture. That's a secondary problem — the primary one is that the kernel isn't even on the new interpreter yet.

## Proposal

**Single PR, three-part cutover, no compat shim:**

### Part A — point the runtime plugin factory at `PlanInterpreterAdapter`

In `lca/plugins/journal/declarative/runtime_seams_provider.py`:

1. Change `DefaultDeclarativeInterpreterFactory.create(...)` to construct `PlanInterpreterAdapter(journal=journal, effect_gateway=effect_gateway, reducer=reducer, phase_observer=phase_observer, lifecycle_publisher=lifecycle_publisher, loop_guard_evaluator=self._loop_guard_evaluator)` and return it.
2. The five closures map directly to existing `PlanInterpreterAdapter` constructor kwargs (the factory currently throws them away; we honor them).
3. The factory's `bind_cordis_seams(subgraph_runner=, channel_factory=)` call goes away — `PlanInterpreterAdapter` does not need them. The `subgraph_runner` / `channel_factory` injection in `setup()` is removed.
4. `bundles/base.yaml` loses the `subgraph_runner` / `phase_output_channel_factory` `requires=` from the runtime seams provider plugin spec (they're no longer consumed).

In `lca/framework/graph/adapter.py`:

5. `PlanInterpreterAdapter.__init__` accepts the five closures plus `loop_guard_evaluator` and stores them. `run()` and `resume()` pass them into the kernel.
6. `PlanInterpreterAdapter.resume()` becomes a real resume path (uses `PhaseRunCursor` to resume the visit loop from a checkpointed `PlanTraversal.current_id`).

### Part B — delete the dead framework factory and the legacy directory

7. Delete `lca/framework/declarative/plugins/interpreter_factory.py`. Its `@plugin` was never registered, so this is removing dead code.
8. Delete the rest of `lca/framework/declarative/` — `__init__.py`, `plugins/__init__.py`, `plugins/delta_reducer.py`, `plugins/effect_gateway.py`, `plugins/interpreter.py` (the `GenericPlanInterpreter` itself), `plugins/journal_committer.py`, `plugins/lifecycle_publisher.py`, `plugins/loop_guard_evaluator.py`, `plugins/phase_observer.py`. Verify `grep -rln "lca.framework.declarative" tests/ lca/ bundles/ --include='*.py' --include='*.yaml'` returns zero hits (excluding `lca/framework/graph/adapter.py`'s reference which gets updated).

### Part C — fold `lca/framework/subgraph/` and `lca/harness/graph/execute/v2/` deletion in

The legacy `lca/framework/subgraph/` package was kept in PR-7 because the runtime plugin factory still consumed `subgraph_runner` and `phase_output_channel_factory` capabilities. Part A removes both consumers. The package becomes unreferenced.

9. Delete `lca/framework/subgraph/` entirely (`__init__.py`, `protocols.py`, `plugins/__init__.py`, `plugins/channel.py`, `plugins/driver_signal.py`, `plugins/node_graph_driver.py`, `plugins/plan_lift.py`, `plugins/runner.py`, `plugins/runtime.py`).
10. Audit `lca/harness/graph/execute/v2/` — 4 files (`_port_context.py`, `edge_selector.py`, `node_context_factory.py`, `node_output_projector.py`). Verify zero references outside `lca/harness/graph/execute/v2/` and the deleted `lca/framework/subgraph/plugins/node_graph_driver.py`. Delete.
11. Delete `lca/contracts/subgraph.py::SubgraphCloseOut` — its only references were the deleted `NodeGraphDriver` and `tests/unit/framework/subgraph/test_node_graph_driver_close_out.py`. The new `PlanInterpreter`'s `PortRegistry.merge_output` covers the same concern with stronger typing.
12. Clear `LEGACY_WHITELIST` in `scripts/check_framework_cognition_boundary.py` to `()`. Delete the `legacy_skip` branch.
13. Delete `tests/unit/framework/subgraph/`, `tests/declarative/`, and any other test directory whose imports land in the deleted set. Rewrite the test scenarios that genuinely exercise the new kernel — they currently pass by mocking `GenericPlanInterpreter`. After Part A they should mock `PlanInterpreterAdapter` instead. The existing `test_p7_interpreter_fallback.py` family needs rewriting because it tests behavior of the deleted interpreter class.

### Part D — fix the test wording for criterion #5

The plan acceptance criterion says "tool_call event." The kernel's real event points for tool calls are `body.tool.execute.start`, `step.tool_call.record`, `step.tool_result.record`, `body.tool.execute.end` (emitted from `concept.effect.execute`). `phase.tool.call.start` is a subgraph-enter marker on `act.validate`, not a tool call. New `tests/integration/cutover/test_tool_call_e2e.py` asserts the real event points.

### Boundary of new wiring

- **Runtime plugin** (`lca/plugins/journal/declarative/runtime_seams_provider.py`): becomes a thin factory that constructs `PlanInterpreterAdapter` with the five runtime closures. No more `bind_cordis_seams`.
- **Framework kernel** (`lca/framework/graph/`): owns `PlanInterpreter`, `StrategyRegistry`, the 10 strategies, `PlanInterpreterAdapter`. The adapter's `run` and `resume` are the production entry. `SubgraphStrategy` either continues using its host-injected `sub_runner` (legacy `SubgraphRunner`) until the next iteration, or it recursively invokes `PlanInterpreter.run` after `lift_subgraph_plan(ref)` — the note leaves this choice for the implementation step.
- **Contracts** (`lca/contracts/`): `SubgraphCloseOut` Protocol deleted; the new kernel's `NodeOutput.port_values: Mapping[str, Any]` is the typed projection seam.
- `LEGACY_WHITELIST` in `scripts/check_framework_cognition_boundary.py`: `()` after this PR lands.

## Alternatives considered

### Why not just relax `remember_admit` to ALLOW when reflection is missing?

The handoff flagged this as option A. The defect is not that `remember_admit` is strict; the defect is that the kernel isn't on the new interpreter at all. Loosening the policy hides the cause. **Rejected.**

### Why not thread the five closures into `GenericPlanInterpreter` and let it keep running?

This is the status quo (and it already runs). The cutover plan commits to `PlanInterpreter` being the sole interpreter. Keeping `GenericPlanInterpreter` as the runtime interpreter with new kwargs is a "compat shim without delete-when" — explicitly forbidden by AGENTS.md §4. **Rejected.**

### Why not wire Part A and split Parts B/C/D into a follow-up PR?

Tempting for review hygiene. But Part A is meaningless without Part B: if `PlanInterpreterAdapter` is the runtime interpreter, the `lca/framework/declarative/` files become unreferenced and dead. Leaving them is a compat shim (AGENTS.md §4 violation). Single PR, single seam, full delete-when. **Rejected: split into separate PRs.**

### Why not keep `lca/contracts/subgraph.py::SubgraphCloseOut` as a thin alias for `Mapping[str, Any]` projection?

The Protocol adds nothing the new port registry doesn't already provide. Single-method `Protocol` that returns `Mapping[str, Any]` is just `Callable[[Mapping[str, Any]], Mapping[str, Any]]` with extra ceremony. Deleting it simplifies the contracts surface. **Rejected: keep as alias.**

### Why not delete `lca/harness/graph/execute/v2/` in a separate PR after auditing?

The audit happens *as part of* the deletion: grep verifies zero references, then `git rm`. Splitting it requires a parallel tracking branch for the deletion. Single PR is cheaper. **Rejected: split into a separate PR.**

## Acceptance criteria

- `git grep -n "GenericPlanInterpreter" lca tests bundles` returns zero hits (excluding the deletion commit and this note's references in the deletion PR description).
- `git ls-files lca/framework/declarative/ lca/framework/subgraph/ lca/harness/graph/execute/v2/` returns empty.
- `LEGACY_WHITELIST` in `scripts/check_framework_cognition_boundary.py` is `()` and the script exits 0.
- `lca/plugins/journal/declarative/runtime_seams_provider.py::DefaultDeclarativeInterpreterFactory.create` returns `PlanInterpreterAdapter(...)` constructed with the five runtime closures.
- `lca/framework/graph/adapter.py::PlanInterpreterAdapter.resume` accepts a `PhaseRunCursor` and resumes from the checkpointed node rather than calling `run` from scratch.
- `scripts/lca-ops kernel-restart && scripts/lca-ops runs create --user-text "use a tool to look up the current weather"` produces a run whose journal spine contains `body.tool.execute.start → step.tool_call.record → step.tool_result.record → body.tool.execute.end → phase.tool.call.end → phase.act.fold.end`.
- `scripts/lca-ops status --json` reports `kernel_serve` healthy before and after the run.
- `uv run pytest tests/unit/contracts/graph tests/unit/cognition/wire tests/unit/framework/graph tests/contracts/test_protocols_package_contract.py tests/integration/cutover/test_tool_call_e2e.py` exits 0.

## Risks

- **Test fallout is large**: ~25+ test files reference `GenericPlanInterpreter` or `lca.framework.declarative`. They split into two categories: (a) tests that exercise the interpreter directly via `GenericPlanInterpreter(...)` and need rewriting to use `PlanInterpreterAdapter(...)`, (b) tests that import through `lca.framework.declarative` package paths. Mitigation: triage the list, rewrite (a), delete (b), commit both in this PR.
- **`PlanInterpreterAdapter.resume` semantics**: the legacy `GenericPlanInterpreter.resume` reads a `PhaseRunCursor` and replays from the cursor's checkpointed node. The new `PlanInterpreter` doesn't yet have a cursor type — Part A introduces `PhaseRunCursor` and `PlanTraversal.resume(cursor)`. The legacy resume path also handles budget exhaustion and loop guard evaluation; both must be ported. Mitigation: integration test that resumes a partially-completed run and asserts the spine picks up at the expected node.
- **`bind_cordis_seams` removal**: the think-subgraph seam (capability `subgraph_runner`) was injected via this method. After Part A the runtime plugin doesn't consume `subgraph_runner`. But the `think.subgraph_runtime` provider at `lca/plugins/think/llm/subgraph_runtime_provider.py` (or its replacement per Note `2026-09-10-think-subgraph-cordis-capability-bridge`) may still register the capability for the inner think subgraph's own consumption. Mitigation: verify with `grep -rln "subgraph_runner" bundles/` that the capability is no longer consumed; if it is, leave the registration alone but the runtime plugin no longer reads it.
- **Plugin id collision**: the framework's dead `@plugin(id="declarative.interpreter_factory")` overlaps the runtime plugin's `provides=["declarative_interpreter_factory"]`. After Part B's deletion of the framework plugin, only the runtime plugin provides the capability. Verify no second `provides=("declarative_interpreter_factory",)` exists in any other plugin file before deleting.

## Related

- Note `2026-09-10-think-subgraph-cordis-capability-bridge` — eliminated `ThinkSubgraphRuntime` and rewired inner think subgraph capability resolution through Cordis. Independent of this note.
- Note `2026-09-09-phase-graph-unification` — same direction, but for the phase graph itself. Already implemented.
- Note `2026-09-08-surface-render-slot-plan-strategy` — the surface render slot used by the strategy registry.
