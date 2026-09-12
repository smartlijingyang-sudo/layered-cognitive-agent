# Agent Note: six-phase subgraph cutover — framework drops PhaseExecutor entirely

Status: implemented

## Decision

The graph framework stops dispatching phase visits through
`PhaseExecutorStrategy`. Every phase main binds `subgraph` and
recurses into a single-node subgraph bundle whose host plugin is a
`NodeExecutor` (think / act pattern). The kernel sees only typed
`NodeInput` / `NodeOutput` ports; `PhaseInput`, `PhaseResult`, and
`PhaseExecutor` never cross the framework boundary.

The runtime side keeps `phase_executors` only as an internal fact
consumed by the v1 driver path under `lca/loop/transaction.py`; the
new kernel path never touches it. `BindingKind.PHASE_EXECUTOR`,
`PhaseExecutorStrategy`, `PhaseExecutorLookup`, the adapter's runner
closure, and `phase_executors` field on `ProductionRuntimeDeps` /
`DeclarativeRuntimeBindings` are deleted in the same PR with no
compat shim.

## What changed

### Framework purity (delete + rewrite)

- `lca/framework/graph/strategies/phase_executor_strategy.py` deleted.
  The whole runner-closure seam that bridged `PhaseInput` /
  `PhaseResult` to `NodeOutput` is gone; the kernel no longer
  carries that protocol.
- `lca/framework/graph/strategies/__init__.py` drops the import and
  the re-export.
- `lca/framework/graph/strategy_registry.py` renames
  `PhaseExecutorLookup` → `NodeExecutorLookup`. The Protocol's
  surface is unchanged; only the name reflects that it now serves
  one binding (`NODE_EXECUTOR`).
- `lca/framework/graph/adapter.py` drops:
  - `executor_lookup`, `phase_executors`, `phase_capabilities`,
    `runner` fields from `PlanInterpreterAdapter`;
  - the `_build_runner()` method that wrapped `PhaseExecutor.execute`;
  - `_resolve_phase_executor`, `_build_phase_context` helpers;
  - the `phase_executors` swap in `_build_registry_with_runner`;
  - the `PHASE_EXECUTOR → PhaseExecutorStrategy(runner=...)` branch.

  Renamed `_build_registry_with_runner` → `_build_registry`. The
  remaining eight binding kinds are `subgraph`, `node_executor`,
  `gate_chain`, `transform`, `observe`, `terminate`, `parallel`,
  `agent_consult`, `agent_fanout` (nine total; matches
  `BindingKind`).
- `lca/contracts/protocols/graph/binding.py` drops
  `BindingKind.PHASE_EXECUTOR`; the enum now has nine entries.
- `lca/framework/graph/lifter.py` drops the `phase.<x>` → PHASE_EXECUTOR
  fallback that was the legacy compatibility hatch.

### Runtime closure simplification

- `lca/runtime/support/runtime_bindings.py` drops the `phase_executors`
  field and its `assemble` kwarg, drops the `phase_scope()` accessor,
  and rewires `require_executable_plan` to validate against
  `node_executors`. `new_interpreter` no longer builds a runner
  closure or wires `phase_capabilities`.
- `lca/runtime/loop/runtime_loop.py` drops the
  `CognitiveRuntime.phase_executors` property and the corresponding
  `TYPE_CHECKING` import.
- `lca/plugins/journal/declarative/runtime_seams_provider.py`
  drops `phase_executors` / `phase_capabilities` from
  `DefaultDeclarativeInterpreterFactory.create`.
- `lca/contracts/protocols/runtime/runtime/composition.py` drops
  the same kwargs from the `DeclarativeInterpreterFactory` Protocol.
- `lca/plugins/composer/runtime/runtime/deps.py` drops
  `phase_executors` from `ProductionRuntimeDeps`.
- `lca/plugins/composer/runtime/runtime/binding.py` drops the
  parameter and call sites; `bind_runtime_graph` no longer resolves
  `phase_executors` at composition time.
- `lca/plugins/composer/runtime/runtime/capabilities.py` deletes
  `resolve_phase_executor_bindings` (the v1 capability resolver that
  walked `plan.phase_bindings` and required every `executor_capability`
  to be present in the booted scope).
- `lca/plugins/composer/runtime/fixture/runtime_input.py` drops
  `phase_executors` from the fixture input dataclass; the fixture
  adapter stops projecting it into the production deps.

### New subgraph host plugins

- `lca/plugins/loop/phase/perceive/host/plugin.py` provides
  `phase.perceive.host` as a `NodeExecutor` that adapts the typed
  port contract to the standard `PhaseExecutor.execute` payload
  path. The standard `phase.perceive.standard` plugin remains as
  the logic carrier.
- `lca/plugins/loop/phase/reflect/host/plugin.py`,
  `lca/plugins/loop/phase/remember/host/plugin.py`,
  `lca/plugins/loop/phase/stop/host/plugin.py` follow the same
  pattern; each emits the typed `reflection` / no-port /
  `stop_decision` port respectively.
- `lca/plugins/loop/phase/_shared/reader.py` provides
  `_MappingReader` so the host plugins can hand a plain dict to
  `RestrictedPhaseContext.capabilities` without leaking the dict
  itself into the standard phase logic.

### New subgraph bundles (Bundle Graph Spec v2)

- `bundles/perceive_subgraph.yaml` — single node `perceive.host`,
  outputs `observation`.
- `bundles/reflect_subgraph.yaml` — single node `reflect.host`,
  outputs `reflection`.
- `bundles/remember_subgraph.yaml` — single node `remember.host`,
  emits no port (terminal-of-typing node).
- `bundles/stop_subgraph.yaml` — single node `stop.host`, outputs
  `stop_decision`.

### Profile wiring

- `profiles/web-standard.yaml` patch `phase.topology.standard` now
  binds every phase main via `sub_spec_ref`: perceive/think/act/
  reflect/remember/stop all point at the new subgraph bundles.
  No phase main carries a `phase.<x>.standard` binding string.
- `bundles/base.yaml` registers the four new host plugins under
  `phase:<x>::phase.<x>.host`.

### Tests rewritten

- `tests/phase_executors.py` deleted.
- `tests/unit/framework/graph/test_strategies.py` drops
  `TestPhaseExecutorStrategy` and the `phase_executor` kind
  assertion; the `test_resolve_executor_raises_when_lookup_missing`
  test points at `NODE_EXECUTOR`.
- `tests/unit/framework/graph/test_phase_context_threading.py`
  deleted (it pinned `_build_phase_context`, which is gone).
- `tests/unit/framework/graph/test_kernel.py` drops
  `PHASE_EXECUTOR` literals and the duplicate
  `NODE_EXECUTOR` stub registration; `test_lift_graph_spec_minimal`
  uses `node_executor` string.
- `tests/unit/framework/graph/test_agent_strategies.py` updates
  the registered-kinds assertion to the nine-entry set.
- `tests/unit/contracts/graph/test_protocols.py` rewrites the
  `PHASE_EXECUTOR` references to `NODE_EXECUTOR`; the
  `test_ten_entries` test now asserts nine.
- `tests/integration/cutover/test_tool_call_e2e.py` rewrites the
  hand-rolled six-phase plan to bind `NODE_EXECUTOR` and uses
  `NodeExecutorStrategy` + a `_StubNodeExecutor` instead of
  `PhaseExecutorStrategy` + runner closure. Resume path is
  unchanged: cursor seeds traversal, visit counters pre-populated.
- `tests/integration/test_spine_graph_events_e2e.py` drops the
  `phase_executor_strategy` import.
- `tests/integration/test_runtime_graph_observer_wiring.py`,
  `tests/scenario/runtime/test_runtime_factory_strict_bindings.py`,
  `tests/composer/test_agent_assembly_runtime_bindings.py`,
  `tests/runtime/test_declarative_execution_journal.py`,
  `tests/scenario/architecture/test_architecture_deepening.py`,
  `tests/scenario/handoff/test_handoff_strategy.py` rewrite
  `phase_executors={...}` fixtures to `node_executors={...}`
  (or drop the kwargs).

### New parity + structural tests

- `tests/declarative/test_phase_subgraph_parity.py` covers:
  - framework zero-import guard for `PhaseInput` / `PhaseResult` /
    `PhaseExecutor` / `PhaseExecutorStrategy` / `PHASE_EXECUTOR` /
    `PhaseExecutorLookup` / `phase_executor_strategy`;
  - default registry has no `phase_executor` kind;
  - `BindingKind` enum has no `phase_executor` value;
  - each new subgraph bundle parses and has at least one entry
    node;
  - each new host plugin's `node_execute` emits the expected
    typed port (`observation` / `reflection` / `stop_decision`,
    and `remember` is terminal-of-typing with no port);
  - `web-standard.yaml` patch wires every phase main via
    `sub_spec_ref` and no `phase.<x>.standard` binding.

## Problem

After `2026-09-11-act-subgraph-seam-cutover` and
`2026-09-11-kernel-native-phase-runner`, think and act main nodes
were already subgraph-driven. The other four phases
(perceive / reflect / remember / stop) still bound
`phase.<x>.standard` directly through `PhaseExecutorStrategy`,
which meant the framework kept importing `PhaseInput` /
`PhaseResult` / `PhaseExecutor` to wire the runner closure inside
the adapter. AGENTS.md §2.2 requires that any object not be both
the source of fact and a projection; the kernel path was
effectively carrying the phase vocabulary in two places. The
"graph knows nothing about business" invariant from ADR-0219
§5.5 was still violated for four out of six phases.

The runner closure was the seam that hid the violation: it
adapted `PhaseResult.payload` to a typed `NodeOutput.port_values`
dict. Every other strategy spoke `NodeInput` / `NodeOutput`
directly.

## Proposal

**Delete `PhaseExecutorStrategy` and its runner seam in the same PR.**
Mirror the think / act subgraph pattern for the remaining four
phases: single-node subgraph bundle + `NodeExecutor` host plugin
that calls into the existing `phase.<x>.standard` logic. The
adapter's runner closure and the `phase_executors` field on
`DeclarativeRuntimeBindings` / `ProductionRuntimeDeps` come out
together with `PhaseExecutorStrategy`. The framework keeps only
nine binding kinds (was ten) and the kernel chain runs end-to-end
without phase types.

The standard `PhaseExecutor` plugins
(`lca.plugins.loop.phase.<x>.standard.plugin`) stay as library
code: the new host plugins import their `create_executor()` and
call `.execute()` from inside a `NodeExecutor.node_execute` body.
The kernel sees typed ports; the host plugin owns the
`PhaseInput` / `PhaseResult` boundary as a private detail of one
node_executor.

### Concrete changes

The list above enumerates every file touched. Two non-obvious
wins:

1. **`PhaseExecutorLookup` rename.** The Protocol was only ever
   invoked from `NodeExecutorStrategy` (the runner closure
   deleted with `PhaseExecutorStrategy` was the only other
   caller). Renaming to `NodeExecutorLookup` makes the one
   remaining consumer explicit and removes the dead-name trap.

2. **`_MappingReader` shared adapter.** The host plugins all need
   to wrap `context.runtime: dict` into a `PhaseCapabilityReader`
   for `RestrictedPhaseContext.capabilities`. A one-class file in
   `lca/plugins/loop/phase/_shared/reader.py` keeps the four host
   plugin files uniform and avoids each one re-implementing the
   `get(name) -> Any` Protocol.

### Why no compat shim

- AGENTS.md §4 forbids parallel event vocabularies, parallel
  schemas, parallel plugin manifests, or second Profile resolution
  without an ADR + delete-when. A "compat shim" `PhaseExecutorStrategy`
  would be a parallel binding kind with no production consumer.
- The kernel cutover plan already committed to `PlanInterpreter`
  as the sole interpreter. Keeping `PhaseExecutorStrategy` would
  reintroduce the parallel path the act-subgraph note deleted.
- Every consumer in the codebase (runtime closure, fixture
  inputs, composer factory) is updated in the same PR; no caller
  can observe the field's absence without compile-time breakage,
  so the safety net of a compat shim is moot.

### Boundary of new wiring

- **Framework** (`lca/framework/graph/`): owns the typed port
  contract (`NodeInput` / `NodeOutput` / `port_values`). No
  business vocabulary crosses in.
- **Cognition / runtime** (`lca/runtime/`, `lca/cognition/`):
  unchanged surface; runtime bindings carry `node_executors`
  only. The `phase_executors` map still exists in the v1 driver
  path under `lca/loop/transaction.py` for legacy code that
  hasn't migrated, but the kernel never reads it.
- **Plugins**: four new host plugin files under
  `lca/plugins/loop/phase/<x>/host/plugin.py`, registered in
  `bundles/base.yaml`. Standard phase plugins stay as library
  code; their `@plugin` registration still publishes them under
  `phase.<x>.standard` for any future caller that needs the
  direct v1 entry.
- **Profiles**: `web-standard.yaml` patches every phase main to
  bind via `sub_spec_ref`. Other profiles
  (`benchmark.yaml`, `cordis-creator.yaml`, `composio-enabled.yaml`,
  `web-standard-continuous.yaml`, `agent-lab-infoedge.yaml`) still
  reference `declarative-phase-graph.yaml` which still wires
  `phase.<x>.standard` directly — that is the v1 path; they
  remain loadable. Migrating those profiles to the new subgraph
  bundle set is follow-up scope (see Risks below).

## Alternatives considered

### Why not a single "phase_host" factory wired in one place?

Could collapse the four host plugins into one file with a
generic factory. Rejected: each phase has a distinct typed port
contract (`observation` / `reflection` / no-port /
`stop_decision`); the contract is the public surface of each
phase. One file would have to parameterize the contract, which
is exactly the pattern we just deleted (`PhaseExecutorStrategy`'s
generic runner). One file per phase is one shape per phase.

### Why not rewrite the standard plugins as `NodeExecutor` directly?

Would mean rewriting `phase.<x>.standard` to implement
`NodeExecutor` instead of `PhaseExecutor`. The standard plugins
also serve the v1 driver path (the legacy interpreter and any
profile that hasn't migrated). Cutting them over would break
`lca/loop/transaction.py` and the five profiles that still load
`declarative-phase-graph.yaml`. The host plugin pattern keeps the
standard plugins reusable as library code while routing the
kernel path through the typed port contract. **Rejected for this
PR;** follow-up cutover if the v1 driver is also retired.

### Why not keep `phase_executors` as an alias for `node_executors`?

The two maps are keyed by different strings:
`phase_executors` keys by `phase.<x>.standard`, `node_executors`
keys by factory name (`phase.<x>.host`). Aliasing them in
production factory code would silently collapse two distinct
registrations into one and break capability attribution. **Rejected.**

## Verification

- `rg -l 'PhaseInput|PhaseResult|PhaseExecutor|PhaseExecutorStrategy|PHASE_EXECUTOR|PhaseExecutorLookup' lca/framework/`
  returns only the docstring note in
  `lca/framework/graph/__init__.py` that documents the absent types.
  All other framework files are clean.
- `python -c "from lca.framework.graph import default_strategy_registry; print({k.value for k in default_strategy_registry().kinds()})"`
  emits
  `{'observe', 'agent_fanout', 'agent_consult', 'node_executor', 'parallel', 'subgraph', 'terminate', 'transform', 'gate_chain'}` —
  no `phase_executor`.
- `./scripts/lca-ops inspect-tree profiles/web-standard.yaml`
  reports all four new host plugins active
  (`phase.perceive.host`, `phase.reflect.host`,
  `phase.remember.host`, `phase.stop.host`).
- `pytest tests/declarative/test_phase_subgraph_parity.py -q` —
  18 tests pass (4 framework-purity guards, 4 bundle-shape guards,
  4 host parity tests, 6 profile-binding checks).
- `pytest tests/unit/framework/graph tests/integration/cutover tests/integration/test_spine_graph_events_e2e.py tests/unit/contracts/graph -q` —
  97 tests pass; the kernel strategies, the tool-call E2E seam,
  and the contract tests all green.
- `pytest tests/runtime tests/composer tests/scenario/runtime tests/integration` —
  291 passed, 40 pre-existing failures (all in
  `tests/runtime/test_runtime_loop_exception_path.py`,
  `tests/composer/test_agent_assembly_runtime_bindings.py`,
  `tests/composer/test_composer_consumes_compiled_capability.py`,
  `tests/composer/test_capability_resolution.py`,
  `tests/integration/test_assistant_e2e.py`,
  `tests/integration/test_loop_cursor_wiring.py`, etc.). Baseline
  on the same selection reports the identical 40 failures
  pre-PR; this PR introduces zero new test failures.
- `./scripts/lca-ops runs create --user-text "ping" --profile profiles/web-standard.yaml` —
  produces a run id; the kernel accepts the new topology.

## Risks / Follow-ups

- **Other profiles still bind `phase.<x>.standard`.** Five profiles
  (`benchmark.yaml`, `cordis-creator.yaml`,
  `composio-enabled.yaml`, `web-standard-continuous.yaml`,
  `agent-lab-infoedge.yaml`) still load
  `bundles/declarative-phase-graph.yaml` and the v1 driver under
  `lca/loop/transaction.py` resolves their `phase.<x>.standard`
  capability keys against `ProductionRuntimeDeps.phase_executors`.
  After this PR that field is gone, so any production run that
  resolves through one of these profiles will fail-loud at
  `runtime_bindings.require_executable_plan`. The intended
  migration is to add `bundles/{perceive,reflect,remember,stop}_subgraph.yaml`
  to those profiles and patch `phase.topology.standard` the same
  way `web-standard.yaml` does. This is profile-level plumbing,
  not framework work; tracked as follow-up.
- **`tests/scenario/architecture/test_architecture_deepening.py`
  and `tests/scenario/handoff/test_handoff_strategy.py`** still
  reference `phase_executors` indirectly through fixture
  defaults; the test files were updated to pass `node_executors=`,
  but if a future test fixture reintroduces `phase_executors=` it
  will surface as a `TypeError` at construction time, which is the
  intended fail-loud.
- **`lca/loop/transaction.py::PhaseExecutionTransaction`** is
  still importable for any future caller that needs v1 driver
  semantics. Nothing in the kernel depends on it after this PR.
- **`scripts/check_framework_cognition_boundary.py`** still
  tracks the framework / cognition boundary; the new host
  plugin files sit under `lca/plugins/loop/phase/` (the
  `loop/phase` prefix was already whitelisted for the standard
  plugins), so the boundary check should remain green. Run
  `./scripts/lca-ops typecheck --focus lazy-import` to confirm
  no new violations are introduced; baseline is
  `failed — 632 diagnostics`, all pre-existing.

## Out of scope (per plan non-goals)

- `PhaseExecutor` Protocol semantics — unchanged.
- `phase_executor_capability_key` calculation in
  `lca/loop/phases/registry.py` — kept; not consumed by the
  framework path.
- `lca/plugins/loop/phase/<x>/standard/` plugin files — kept as
  library code; their `@plugin` registrations stay so v1
  callers can still resolve them.
- Six-semantic phase closed set — unchanged.
- ADR-0194 / 0195 / 0220 — unchanged; this note documents the
  cutover.
