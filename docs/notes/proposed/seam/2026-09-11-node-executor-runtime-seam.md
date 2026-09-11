# Agent Note: kernel-native node-executor runtime seam

Status: proposed

## Problem

The kernel-native phase runner closure (note `2026-09-11-kernel-native-phase-runner`, partly landed on `main`) wires the new kernel to `phase.<phase>.standard` executors. The closure resolves a phase executor by capability key (e.g. `phase.perceive.standard`) and invokes `executor.execute(RestrictedPhaseContext, PhaseInput)`. `perceive.main` runs end-to-end and emits `memory.read`.

After perceive, the kernel reaches `think.main` which is a `sub_spec_ref` to `bundles/think.yaml`. The kernel lifts the subgraph and dispatches into `think.shortcut`. That node's plugin (`lca/plugins/think/shortcut.py`) is a `NodeExecutor`, not a `PhaseExecutor`. It reads `context.runtime` (a `SubgraphRuntime`-shaped object with a `resolve(capability)` method). Today `NodeExecutorStrategy.execute` builds the legacy `NodeContext` with `runtime=context.node_config.get("runtime", {})` — i.e. an empty dict — so the executor calls `runtime.resolve("supports_shortcut")` and crashes with `'NoneType' object has no attribute 'resolve'`.

The kernel cannot complete a tool-call run until this seam is closed.

## Proposal

**Build a kernel-native `NodeExecutorRuntime` and wire it through the adapter's strategy registry.**

The runtime needs to satisfy the same `SubgraphRuntime` Protocol (`resolve(capability) -> object | None`) the think nodes already use, but resolve against the new kernel's typed context instead of the legacy Cordis context. Three concrete steps:

### A. Add `node_executor_runtime` constructor kwarg

`PlanInterpreterAdapter.__init__(node_executor_runtime=...)`. The runtime is a `SubgraphRuntime`-shaped object. When `None`, the adapter builds a default that returns `None` for any capability (mirrors the legacy `PluginContextBackedRuntime` fallback).

### B. Pass it from the runtime factory

Extend `DeclarativeInterpreterFactory.create(...)` once more with `node_executor_runtime=...` kwarg. Wire `RuntimeBindings.new_interpreter()` to pass the runtime built from `RuntimeBindings` capability map (or a new dedicated runtime if needed).

### C. Bridge in the kernel

`NodeExecutorStrategy.execute` reads `runtime = context.node_config.get("node_executor_runtime") or context.node_config.get("runtime") or NodeExecutorRuntime.empty()` and constructs `LegacyNodeContext(runtime=runtime, ...)`. The think nodes see a `runtime` whose `resolve(name)` returns the right capability (or `None` if missing, mirroring `PluginContextBackedRuntime`).

### Concrete implementation

1. In `lca/framework/graph/adapter.py`:
   - Add a `NodeExecutorRuntime` Protocol and a `_MappingNodeExecutorRuntime` implementation that wraps a `Mapping[str, object]` and returns `None` on missing keys.
   - Construct one in `__post_init__` from `self.capabilities` (the same `RuntimePhaseCapabilities` already passed to the adapter). The mapping keys are already the canonical capability names.
   - Wire the runtime into the per-adapter `StrategyRegistry` via a new constructor kwarg on `NodeExecutorStrategy` (or a `runtime_setter` closure on the registry).

2. In `lca/contracts/protocols/runtime/runtime/composition.py`:
   - Drop the `NodeExecutorRuntime` Protocol here (or re-export). Add `node_executor_runtime: object | None = None` to `DeclarativeInterpreterFactory.create`.

3. In `lca/runtime/support/runtime_bindings.py`:
   - `RuntimeBindings.new_interpreter()` passes `node_executor_runtime=self.capabilities` to `interpreter_factory.create(...)`.

## Alternatives considered

### Why not route think nodes through PhaseExecutors (unify phase_executor and node_executor strategies)?

The phase executor and node executor have different contracts: `PhaseExecutor.execute(context: PhaseContext, input: PhaseInput) -> PhaseResult` is sync-after-await and reads `context.results_by_phase`; `NodeExecutor.execute(context: NodeContext, input: NodeInput) -> NodeOutput` is async and reads `context.runtime`. Unifying them dissolves a real semantic boundary (think nodes have a runtime, phase nodes have a journal + reducer). Rejected.

### Why not use the legacy `PluginContextBackedRuntime` directly?

It lives in `lca.framework.subgraph.plugins.runtime` (now deleted). The new kernel has no Cordis context to back it. The simpler kernel-native mapping (`Mapping → resolve(name)`) covers all think-node capability reads without re-introducing Cordis at this layer.

### Why not fold this into the kernel-native phase-runner note (2026-09-11-kernel-native-phase-runner)?

It's a separate seam. The phase runner note handles `phase.<phase>.standard` executors; the think nodes use a different Protocol and a different runtime object. Combining them would conflate two adjacent-but-distinct fixes.

## Acceptance criteria

- `NodeExecutorStrategy.execute` constructs a `LegacyNodeContext` whose `runtime` is a kernel-native `NodeExecutorRuntime` (mapping-backed) when the adapter receives one.
- `node_executor_runtime` kwarg flows from `RuntimeBindings.new_interpreter()` through `DeclarativeInterpreterFactory.create()` to `PlanInterpreterAdapter.__init__()`.
- `scripts/lca-ops runs create --user-text "use a tool to look up the current weather"` produces a run whose journal spine reaches `act.main` (or `body.tool.execute.start` if act subgraph dispatch lands first).
- All `tests/unit/contracts/graph`, `tests/unit/cognition/wire`, `tests/unit/framework/graph`, `tests/integration/cutover` tests pass.

## Risks

- **Capability map shape mismatch**: `RuntimePhaseCapabilities` keys are not necessarily the same names `think.shortcut` looks up (e.g. `supports_shortcut` is a known capability). If the keys don't match, `resolve(name)` returns `None` and the think node's None-handling kicks in (which it already does). Net: a degraded but functional run, not a crash.
- **Test fallout**: legacy tests that constructed a `NodeContext` with a Cordis-backed runtime need updating to use the mapping-backed runtime. Mitigation: keep both APIs side by side; `NodeExecutorStrategy` reads either shape.

## Related

- Note `2026-09-11-kernel-native-phase-runner` — landed phase runner closure; this note is the next adjacent seam.
- Note `2026-09-11-act-subgraph-seam-cutover` — landed the kernel cutover; this note extends it to the think subgraph path.
- Note `2026-09-10-think-subgraph-cordis-capability-bridge` — eliminated the legacy `ThinkSubgraphRuntime` wrapper; this note does the same for the kernel-native path.
