# Think Subgraph Flatten — Design Spec

**Date:** 2026-09-09
**Status:** locked (post-brainstorming)
**Path:** replaces `phase.think.subgraph_host` + `lca/plugins/loop/phase/think/subgraph/_shared.py`

## 1. Goal

Remove the temporary `_shared.py` glue from the think subgraph and make each
of the five think steps (`shortcut / route / reason / classify / gate`) an
independent L2 phase plugin. Delete the `phase.think.subgraph_host` container
plugin and replace it with a thinner `phase.think.orchestrator` whose sole job
is to drive the `SubgraphPhaseRunner`.

After this change the think subgraph has the same shape as
`agent_lab/graphs/configs/act.yaml`: five flat, independently registered
phase plugins, no private `_shared.py` aggregator.

## 2. Background

The current `phase.think.subgraph_host` was introduced as a temporary cutover
(see `history/2026-09/think-subgraph-default-cutover/`). Five step plugins
under `lca/plugins/loop/phase/think/subgraph/<step>/plugin.py` delegate their
work to `run_<step>_step` functions in a shared `_shared.py` file. That
shared file also defines `ThinkSubgraphCarry`, `ThinkCollaborators`, and a
`collaborators_from_brain` helper that reflects on `Brain` to extract
`reasoner / classifier / decision_gate / skill_router / reducer / agent_gates`.

The reflection path violates C13 (information lineage closure): the type
contract is implicit (`getattr(brain, "reasoner", None)`), missing
configuration fails silently, and replacing a single step requires
modifying the whole `Brain` assembly. The `using-superpowers` skill
referenced by external tooling on top of this path is a workaround for the
fact that the real entry point (a phase graph with five flat plugin nodes)
does not exist yet.

## 3. Decisions

### 3.1 Carry handling — option α

`ThinkSubgraphCarry` is preserved as a typed data class but moved into
`lca/contracts/models/core/execution/think_carry.py`. The
`SubgraphPhaseRunner._drive_linear_subgraph` loop in
`lca/harness/graph/execute/subgraph_phase_runner.py` becomes responsible for
creating, reading, and writing back the carry; the five step plugins do not
import or reference the carry type at all.

Rationale: keeps the runtime responsible for cross-node plumbing, leaves
each plugin to focus on a single capability call, and mirrors how act and
reflect subgraphs use the runner.

### 3.2 Shortcut capability is independent of gate

Today `_shared.run_shortcut_step` does `isinstance(decision_gate, SupportsShortcut)`.
The flatten makes `phase.think.shortcut` an independent capability key.
Profile assembly may register the same `SupportsShortcut` object under both
`phase.think.shortcut` and `phase.think.gate`, but the step plugin does not
reach into the gate capability to find the shortcut.

If `phase.think.shortcut` is not provided, the step returns
`stage_result(carry)` and the graph continues from `route`. Missing shortcut
is not an error — `SupportsShortcut` is documented as optional.

### 3.3 Orchestrator plugin

`phase.think.orchestrator` replaces `phase.think.subgraph_host`. Its only
responsibility is to resolve the `SubgraphPhaseRunner` capability and call
`run_terminal_subgraph(plan_ref, entry_node, context, input)`. It does not
import any step plugin, does not know what the five steps are, and does not
reference `Brain`.

### 3.4 Bundle shape

`bundles/think-orchestrator-graph.yaml` declares five phase graph nodes:
`think.shortcut / think.route / think.reason / think.classify / think.gate`,
each bound directly to its corresponding L2 phase plugin. The four edges
preserve current behaviour (shortcut exits the graph on `result_kind ==
"decision"`, the remaining edges are unconditional).

## 4. File map

### Delete (same PR, no shim)

- `lca/plugins/loop/phase/think/subgraph/_shared.py`
- `lca/plugins/loop/phase/think/subgraph_host/plugin.py`
- `lca/plugins/loop/phase/think/subgraph_host/__init__.py`
- `bundles/think-subgraph-host.yaml`
- `bundles/think-subgraph.yaml`
- `bundles/think-subgraph-graph.yaml`
- `bundles/think-subgraph-steps.yaml`
- `profiles/fixtures/think-subgraph-compile.yaml`
- `tests/cognition/test_think_subgraph_parity.py`

### Create

- `lca/contracts/models/core/execution/think_carry.py`
- `lca/plugins/think/shortcut/plugin.py`
- `lca/plugins/think/route/plugin.py`
- `lca/plugins/think/reason/plugin.py`
- `lca/plugins/think/classify/plugin.py`
- `lca/plugins/think/gate/plugin.py`
- `lca/plugins/loop/phase/think/orchestrator/plugin.py`
- `bundles/think-orchestrator.yaml`
- `bundles/think-orchestrator-graph.yaml`
- `profiles/fixtures/think-orchestrator-compile.yaml`
- `tests/think/test_shortcut_phase_plugin.py`
- `tests/think/test_route_phase_plugin.py`
- `tests/think/test_reason_phase_plugin.py`
- `tests/think/test_classify_phase_plugin.py`
- `tests/think/test_gate_phase_plugin.py`
- `tests/think/test_orchestrator_graph.py`

### Modify

- `lca/harness/graph/execute/subgraph_phase_runner.py` — owns the carry loop.
- `profiles/web-standard.yaml` — `think.main` binding:
  `phase.think.subgraph_host` → `phase.think.orchestrator`.
- `profiles/think-subgraph-dev.yaml` — same binding swap; comment update.
- `docs/notes/implemented/` (any reference to the old plugin ids; to be
  audited during implementation).

## 5. Capability key map

| Plugin id | provides | requires |
|---|---|---|
| `phase.think.shortcut` | `phase.think.shortcut` | — |
| `phase.think.route` | `phase.think.route` | `phase.think.reducer` |
| `phase.think.reason` | `phase.think.reason` | — |
| `phase.think.classify` | `phase.think.classify` | — |
| `phase.think.gate` | `phase.think.gate` | — (reads `phase.think.gate` for `decision_gate`, plus `agent_gates` from `Brain.decision_gate` resolution) |
| `phase.think.orchestrator` | `phase.think.orchestrator` | `SUBGRAPH_PHASE_RUNNER_CAPABILITY` |

`phase.think.reducer` is the existing `Reducer` capability already provided
elsewhere in the system; the new `route` plugin reads it directly via
`context.capabilities`.

## 6. Invariant impact

- C1 cognitive closed set: unchanged.
- C2 dual planes: unchanged.
- C3 facts traceable: each step plugin emits its own
  `phase_think_<step>.checked` / `phase_think_<step>.served` evidence
  descriptors; better than today.
- C4 reducer single writer: unchanged.
- C5 capability monotone: improved — missing capability fails loud at the
  step that needs it, instead of silently falling back through the
  reflection path.
- C6 minimisation: `_shared.py` and `subgraph_host` are deleted.
- C7 control/observation: unchanged.
- C8 determinism: unchanged.
- C9 idempotent/reentrant: unchanged.
- C10 execution narrow gate: unchanged (no new side effects).
- C11 closed event set: five new `phase_think_<step>.checked/served`
  descriptors; added to the EP whitelist during implementation.
- C12 reducer contract: unchanged.
- C13 lineage closure: improved — `PhaseContext.capabilities["phase.think.<step>"]`
  is a typed contract, replacing `getattr(brain, "<attr>")` reflection.

## 7. Verification matrix

| Check | Command |
|---|---|
| Five plugin shapes | `uv run pytest tests/think/test_{shortcut,route,reason,classify,gate}_phase_plugin.py -q` |
| Orchestrator end-to-end | `uv run pytest tests/think/test_orchestrator_graph.py -q` |
| Carry type not leaking | `grep -rn "ThinkSubgraphCarry\|run_shortcut_step\|run_route_step\|run_reason_step\|run_classify_step\|run_gate_step" lca/plugins/ 2>/dev/null` returns empty |
| Old plugin ids gone | `grep -rn "phase.think.subgraph" lca/ profiles/ bundles/ tests/ 2>/dev/null` returns empty |
| Topology compiles | `uv run python -m lca_kernel serve --profile profiles/fixtures/think-orchestrator-compile.yaml --validate` |
| Production profile boots | `uv run python -m lca_kernel serve --profile profiles/web-standard.yaml` |
| Plugin source | `./scripts/lca-ops why-plugin phase.think.orchestrator --profile profiles/web-standard.yaml` |
| Lint | `uv run ruff check lca/ tests/` |
| Type-check | `uv run mypy lca/` |

## 8. Out of scope

- `phase.think.standard` (kept registered, still not bound in any production
  phase graph).
- `Brain` protocol (kept; reflect still uses it).
- `reflect` subgraph, `act`, `perceive`, `remember`, `stop`.
- The `agent_lab` InfoEdgeSpec graph (figure A).
- The `using-superpowers` skill entry itself — once this PR lands, the
  consuming workflow retires its reference, but that is a separate change.

## 9. Risks

1. **Profile load order.** The five new plugin ids must be registered before
   `phase.topology.standard` resolves the new bundle. Implementation order:
   bundle change lands in the same PR as the new plugins, validated by the
   compile-fixture profile before the production profile change.
2. **Shortcut ordering.** Without `isinstance(gate, SupportsShortcut)`,
   profiles must opt-in by registering the shortcut capability explicitly.
   Default production profiles provide it.
3. **Carry loss on reload.** The runner now holds the carry in a `dict` slot
   keyed by `CARRY_KEY`. If a hot-reload occurs between steps, the carry is
   lost; current behaviour is the same — this risk is not new, only
   documented.
