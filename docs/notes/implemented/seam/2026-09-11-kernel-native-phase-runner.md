# Agent Note: kernel-native PhaseRunner closure for the unified graph kernel

Status: implemented

## Problem

The act-subgraph seam cutover (Note `2026-09-11-act-subgraph-seam-cutover`, landed on `main`) closed the runtime factory cutover: `PlanInterpreterAdapter` is what the kernel builds and runs. The kernel boots, the lifter marks the entry node, the strategy registry has all 10 bindings registered. But the kernel still can't run a tool-call prompt to completion:

```
$ ./scripts/lca-ops runs create --user-text "use a tool to look up the current weather"
run_0d7a2a4c444e  failed  H6
kernel.log: RuntimeError('PhaseExecutorStrategy.execute called without runner; ...')
```

The failure is the missing `PhaseRunner` closure on `PhaseExecutorStrategy`. The adapter stores the five runtime closures (`journal`, `effect_gateway`, `reducer`, `phase_observer`, `lifecycle_publisher`) but does not build the runner that bridges the new kernel's `StrategyContext` to a `PhaseResult`. The seam docstring on `PhaseExecutorStrategy` says "the host must inject one (typically via `PhaseExecutionTransaction`)" — but `PhaseExecutionTransaction.run()` takes 10 kwargs (`node_id`, `semantic_phase`, `executable_node`, `state`, `budget`, `plan_ref`, `traversal`, `visit_count`, `capabilities`, `effect_policy`) and the new kernel's `StrategyContext` only carries `plan_ref`, `node_id`, `binding_kind`, `node_config`, `subgraph_ref`, `chain`.

`PhaseExecutionTransaction` is also tightly coupled to the legacy `RestrictedPhaseContext` and the legacy `PhaseTraversal` (per-run, not per-`Plan`); bridging to it would require reconstructing both inside the new kernel — which is a leaky abstraction because the new kernel's `PlanTraversal` is a different object with different semantics.

The kernel can't ship a real run until the runner is built. AC #5 of the cutover plan stays unmet.

## Proposal

**Build a kernel-native `PhaseRunner` closure inside `PlanInterpreterAdapter`.** The closure:

1. Receives `(PhaseInput, StrategyContext) -> PhaseResult` from `PhaseExecutorStrategy`.
2. Resolves the phase executor for `(binding=PHASE_EXECUTOR, node_id)` via a host-injected `PhaseExecutorLookup` (the Protocol already exists in `lca/framework/graph/strategy_registry.py`; today `PlanInterpreterAdapter.executor_lookup = None`).
3. Builds a minimal `RestrictedPhaseContext`-equivalent with `journal=self._journal`, `effect_gateway=self._effect_gateway`, `reducer=self._reducer`, `phase_observer=self._phase_observer`, `state=node_config["agent_state"]`, `budget=state.budget`, `plan_ref=ctx.plan_ref`, `results_by_phase={}` (single-visit semantic for the new kernel).
4. Calls `executor.execute(context, prepared_input)`.
5. Wraps the returned `PhaseResult` for the new kernel's `NodeOutput` projection.

The adapter owns the runner. It carries a single `PhaseTraversal` instance across `PlanInterpreter.run()` calls (one per plan) so `results_by_phase` accumulates across visits and `RestrictedPhaseContext.payload_of(phase, T)` reads from the mirror — matching what `PhaseExecutionTransaction` does today.

### Concrete changes

In `lca/framework/graph/adapter.py`:

1. Add a `_build_runner()` method that returns a closure matching `PhaseRunner = Callable[[PhaseInput, StrategyContext], PhaseResult]`.
2. The runner resolves the executor via `self._executor_lookup(binding=ctx.binding_kind, node_id=ctx.node_id, region=None)`; if `executor_lookup is None`, raise `RuntimeError("...")` with a message telling the host to inject one (currently the error path is `executor_lookup is None` → can't resolve → fall back to a stub that returns `PhaseResult(result_kind="phase_error", ...)`). Today's kernel raises "no strategy registered" because the registry is empty.
3. Initialize `self._phase_traversal = PhaseTraversal(plan)` per `run()` call so the runner can update `results_by_phase` as visits complete. `PlanInterpreter.run` already accepts `traversal=` so the adapter can pre-build it; the runner reads from the same instance.
4. The runner emits `runtime.reducer.apply method=apply_perception / apply_observation / ...` journal events via `self._journal.append(...)` to match the legacy interpreter's spine shape. Each phase plugin's `execute()` is responsible for emitting the inner phase events; the runner only emits the visit-envelope events.

In `lca/plugins/journal/declarative/runtime_seams_provider.py`:

5. The `setup()` function reads `ctx.require("phase_executor_lookup")` if available and passes it to `DefaultDeclarativeInterpreterFactory`. The factory stores it on `PlanInterpreterAdapter.executor_lookup` at `create()` time.

In `lca/plugins/`:

6. New provider plugin `lca/plugins/loop/graph/runtime/phase_executor_lookup_provider.py` with `@plugin(id="phase.executor_lookup.provider", provides=("phase_executor_lookup",))` that constructs the lookup from `ctx.require("phase_executor")` etc., matching the resolver the legacy interpreter used. The provider is registered in `bundles/base.yaml`.

### Why a kernel-native runner, not a bridge to `PhaseExecutionTransaction`

- **Different state models.** `PhaseExecutionTransaction` is designed for the legacy `PhaseTraversal` whose `results_by_phase` is keyed by `SemanticPhase` and lives across all visits. The new kernel's `PlanTraversal` is per-`Plan` and uses `BindingKind`. Building the legacy shape inside the kernel means carrying two cursors for the same run.
- **Capability decays.** `PhaseExecutionTransaction.run` requires `EffectPolicyPlan`, `PhaseCapabilityReader`, `PlanRef`-typed state — none of which the new kernel models. Bridging requires fake objects that satisfy the type system without doing real work, which is exactly the "silent fake default" pattern the agent contract forbids.
- **Phase plugins already handle `context.payload_of(phase, T)`.** The `RestrictedPhaseContext.payload_of` API is what phase plugins read. Building a kernel-native context that implements the same protocol is the smallest viable seam; the phase plugins don't change.
- **It shrinks the seam over time.** Each phase visit that the runner completes goes through the kernel's typed `VisitRecorder`. That data is the SSOT the new kernel's projections will read. Bridging to the legacy transaction would keep two SSOTs alive.

### Boundary of new wiring

- **Framework** (`lca/framework/graph/`): owns the runner closure construction. `PlanInterpreterAdapter.__init__` accepts `executor_lookup: PhaseExecutorLookup | None`. `_build_runner()` returns a `PhaseRunner` and `PlanInterpreter(registry=..., recorder=...)` is constructed with `runner=self._runner`.
- **Cognition / runtime** (`lca/cognition/`, `lca/runtime/`): unchanged. The phase executors under `lca/plugins/loop/phase/*/standard/` already implement the `PhaseExecutor.execute(context, input) -> PhaseResult` protocol.
- **Plugins**: one new provider plugin (`phase.executor_lookup.provider`) registered in `bundles/base.yaml`.
- The legacy `lca/loop/transaction.py::PhaseExecutionTransaction` stays untouched. It's still importable for any future caller that wants the legacy semantics; nothing in the kernel depends on it after this note lands.

## Alternatives considered

### Why not bridge to `PhaseExecutionTransaction`?

The shim approach. The new kernel would carry a fake `PhaseTraversal` whose `results_by_phase` is a mock that reads from the new kernel's `PlanInterpreter` artifacts. Two state models for one run = bugs waiting to happen. The cost of building the bridge is comparable to the cost of building the kernel-native runner, and the bridge is dead weight once phase execution is fully native. **Rejected.**

### Why not make every phase plugin a strategy itself (one strategy per phase)?

That's the long-term direction but a much larger refactor: it dissolves `BindingKind.PHASE_EXECUTOR` into 6 sub-bindings (`PHASE_PERCEIVE`, `PHASE_THINK`, `PHASE_ACT`, `PHASE_REFLECT`, `PHASE_REMEMBER`, `PHASE_STOP`). It changes the `Plan` DTO and the lifter and the topology YAML. Out of scope for this note; a separate ADR can propose it. **Rejected for this PR.**

### Why not return a stub `PhaseResult` from the runner so the kernel "completes"?

That converts a fail-loud into a fail-silent. The run would terminate "successfully" with empty Observation/Reflection, and remember_admit would deny — the same symptom as before, but now hidden behind a "successful" visit. **Rejected.**

### Why not just keep `GenericPlanInterpreter` alongside the new kernel and let profiles choose?

AGENTS.md §4 prohibits parallel paths without an owner and a delete-when. The cutover plan commits to `PlanInterpreter` as the sole interpreter. Two interpreters = permanent compat shim. **Rejected.**

## Acceptance criteria

- `PlanInterpreterAdapter.__init__` accepts `executor_lookup` and constructs a real `PhaseRunner` closure.
- `PlanInterpreter.run` constructs `PlanInterpreter(registry=..., recorder=..., runner=self._runner, traversal=self._phase_traversal)` so the runner can mutate `results_by_phase` across visits.
- `bundles/base.yaml` registers the new `phase.executor_lookup.provider` plugin.
- `scripts/lca-ops runs create --user-text "use a tool to look up the current weather"` produces a run whose journal spine contains the canonical phase event sequence: `perceive → think → act (tool_call.start → tool_call.end) → reflect → remember → stop`.
- `runtime.reducer.apply method=apply_perception / apply_observation / apply_reflection` events fire from the runner's journal appends, matching the legacy interpreter's spine shape so the existing observability consumers stay green.
- `uv run pytest tests/unit/contracts/graph tests/unit/cognition/wire tests/unit/framework/graph tests/integration/cutover -q --no-cov` exits 0; new test added in `tests/unit/framework/graph/test_phase_runner.py` covering the kernel-native runner against a fake executor.
- `scripts/lca-ops status --json` reports `kernel_serve` healthy before, during, and after the tool-call run.

## Risks

- **Two `PhaseTraversal` shapes**: the new kernel's `PlanTraversal` and the runner's `PhaseTraversal` are different objects. Mitigation: keep them in separate fields on the adapter; only the runner reads/writes the legacy shape.
- **Capability keys**: the `PhaseExecutorLookup` Protocol is intentionally narrow (`(binding, node_id, region) -> Any`). Phase plugins today resolve executors by `ctx.capabilities.get("phase.reflect.standard")` etc. The lookup must map `node_id` (e.g. `reflect.main`) to the right capability key. Mitigation: the provider plugin derives the mapping from the legacy node-id → semantic-phase resolution that `agent_lab.profile_loader.build_region_only_phase_graph` already does.
- **Effect dispatch**: the legacy `PhaseExecutionTransaction` calls `effect_gateway.dispatch(command_envelope)` after a successful phase visit. The kernel-native runner must do the same. Mitigation: the runner calls `self._effect_gateway.dispatch(result.command_envelope)` if `result.command_envelope is not None`.
- **Tests**: ~20 unit tests in `tests/declarative/` previously exercised `PhaseExecutionTransaction` directly. They were deleted in the prior PR. New tests in `tests/unit/framework/graph/test_phase_runner.py` cover the new closure against a fake executor; the integration test in `tests/integration/cutover/test_tool_call_e2e.py` is the end-to-end proof.

## Related

- Note `2026-09-11-act-subgraph-seam-cutover` — landed; this note is the next seam.
- Note `2026-09-10-think-subgraph-cordis-capability-bridge` — eliminated the `ThinkSubgraphRuntime` wrapper class with the same "delete the wrapper, build a kernel-native seam" approach.
