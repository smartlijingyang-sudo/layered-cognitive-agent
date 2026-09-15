# Agent Note: Unified nodes directory layout — single `lca/nodes/` tree by region

Status: proposed

## Problem

After ADR-0227 (`@graph_node` DSL) landed, graph nodes exist in three different physical locations with no unifying layout convention:

| Layer | Path | Examples |
|---|---|---|
| `framework` | `lca/framework/graph/nodes/` | `decorator.py`, `history_assemble.py`, `llm_dispatch.py`, `decision_parse.py` |
| `plugins` (think) | `lca/plugins/think/*.py` and `lca/plugins/think/<node>/__init__.py` | `shortcut.py`, `gate.py`, `route.py`, `reason/plan.py`, `reason/render.py`, `history_assemble/__init__.py` |
| `plugins` (loop) | `lca/plugins/loop/graph/nodes/<role>/plugin.py` | `agent/plugin.py`, `aggregator/plugin.py`, `topology/plugin.py`, `registry/plugin.py` |

A new author who wants to "add a think node" must answer three questions that the file system does not answer:

1. Should the body live in `lca/framework/graph/nodes/` (DSL target) or `lca/plugins/think/<node>/__init__.py` (plugin carrier)? The PR2 conversions split this between the two: `history_assemble.py` lives in `framework/graph/nodes/`, but `shortcut.py` (still hand-written) lives in `plugins/think/`. There is no rule.
2. Should the file be flat (`plugins/think/shortcut.py`) or in a sub-package (`plugins/think/history_assemble/__init__.py`)? `reason/plan.py` is one file; `history_assemble/__init__.py` is a package; both register under `think::*`. The bundler doesn't care; readers do.
3. Where do loop's graph-node-executor types (`agent` / `aggregator` / `topology` / `registry`) go? They are not `think::*`; they implement `NodeExecutor` for the outer loop. Today they live under `plugins/loop/graph/nodes/`. There is no cross-reference between think's nodes and loop's nodes — the directory tree hides the fact that they share the same Protocol.

The PR3 plan (`docs/superpowers/plans/2026-09-15-pr3-graph-node-dsl.md`) and the `docs/design/naming-constitution.md` `phase_*` → `phase_graph/` merge both note the problem in passing but neither fixes it; the work is to land a single directory convention and migrate all node files in one PR.

The semantic anchor is the `region` field (ADR-0227 §Decision §3: six-phase closed set `{perceive, think, act, remember, reflect, stop}`). A node's region is the only thing that changes between nodes in different phases; today the region is encoded in the plugin id (`phase.<region>.<id>`) and in the composite-key registration (`<region>::<id>`), but **not** in the file path. The path encodes "which file got there first" instead of "what graph region the node belongs to".

## Proposal

Unify all graph-node implementations under a single new top-level tree `lca/nodes/`, organised as **region → functional sub-group → node**:

```
lca/nodes/
├── think/
│   ├── route/                         # graph access sub-group (shortcut, route)
│   │   └── shortcut.py
│   │   └── route.py
│   ├── reason/                        # LLM-backed reasoning sub-group
│   │   ├── plan.py                    # think.reason.plan
│   │   └── render.py                  # think.reason.render
│   ├── decision/                      # decision-shape sub-group
│   │   └── parse.py                   # think.decision.parse
│   ├── history/                       # session-history sub-group
│   │   └── assemble.py                # think.history.derive (was history_assemble.py)
│   ├── dispatch/                      # LLM I/O sub-group
│   │   └── llm.py                     # think.llm.dispatch
│   └── gate.py                        # think.gate (Gate原语; sub-group = single node)
├── loop/                              # outer loop graph_node_executors
│   ├── agent/
│   │   └── plugin.py
│   ├── aggregator/
│   │   └── plugin.py
│   ├── topology/
│   │   └── plugin.py
│   └── registry/
│       └── plugin.py
├── perceive/                          # empty for now; reserved per six-phase closed set
├── act/
├── remember/
├── reflect/
└── stop/
```

Rules:

- **Region is the first directory level.** `lca/nodes/<region>/<sub-group>/<node>.py` for nodes with sub-groups; `lca/nodes/<region>/<node>.py` for single-node sub-groups (`think/gate.py`).
- **All six phase regions exist as directories** (perceive / think / act / remember / reflect / stop), even when empty — the directory tree mirrors the closed-set.
- **Loop's graph-node-executors** (`agent` / `aggregator` / `topology` / `registry`) live under `lca/nodes/loop/`. These are not think nodes; they implement `NodeExecutor` for the outer runtime loop. They are siblings to `lca/nodes/think/`, not children.
- **Plugin id and composite key are unchanged.** `phase.think.shortcut` and `think::think.shortcut` continue to be the discovery keys; the bundler (`bundles/*.yaml:plugins:`) does not need to change. Only the Python import path changes.
- **`lca/framework/graph/nodes/decorator.py` stays at the framework layer.** The decorator is a primitive used by node authors; it is not a node itself. It moves to `lca/framework/graph/nodes/decorator.py` only if we are also reorganising `framework/graph/`, which is out of scope here.
- **Tests migrate with the file.** `tests/unit/plugins/think/test_shortcut_phase_plugin.py` → `tests/unit/nodes/think/route/test_shortcut.py`. Tests follow the source layout (the existing `tests/unit/plugins/think/` directory becomes empty and is deleted).

### Boundary with ADR-0227 and ADR-0226

- ADR-0227 §Decision specifies the `@graph_node` decorator and its registration contract. This note does not change that contract; it only changes the physical location of files implementing the contract.
- ADR-0226 §5 deferred the `RunSessionWriter` plugin slot to PR3 "once the `@graph_node` DSL provides a typed way to express the seam". The seam is now expressed (`@graph_node(inputs=("state", "writer"))`); this note does not move that seam, it only changes where the nodes that use it live.

### Migration mechanics

1. `git mv` each node file to the new path (preserves blame).
2. Update `from lca.framework.graph.nodes.X import Y` and `from lca.plugins.think.X import Y` references in (a) `lca/plugins/think/__init__.py` and the per-node `__init__.py` re-export shims, (b) test files, (c) any other consumers (currently `tests/support/graph_node_executors.py` is the only consumer outside the node files themselves).
3. The new path replaces the old path **in the same commit**; no re-export shims, no compatibility window. AGENTS.md §4 COMPAT principle: a shim without a delete-when is 红灯; this PR is the delete-when.

### What this proposal does NOT do

- It does not change `@plugin` or `@graph_node` semantics.
- It does not change `region` semantics or the six-phase closed set.
- It does not reorganise `lca/framework/graph/` (the runtime kernel).
- It does not move the `decorator.py` itself.
- It does not change `bundles/*.yaml` (plugin ids are unchanged).
- It does not introduce sub-package vs flat-file rules — the rule "region → sub-group → node" is fixed; per-region sub-group naming is per-region decision (think uses `route/` for shortcut/route; act may use `body/` etc.).

## Alternatives considered

### Why not keep the existing layout and only add a README index?

The README would be a man-maintained index that drifts from the filesystem. Two readers of `lca/plugins/think/shortcut.py` and `lca/framework/graph/nodes/history_assemble.py` would discover the `@graph_node` link only by following README breadcrumbs. The contract is "where do I add a new node" — that must be answerable by `ls` without reading docs.

### Why not flat `lca/nodes/<region>_<node>.py` (region as filename prefix)?

Region is the primary axis of the cognitive closed set (ADR-0227 §Decision §3). Burying it in the filename hides the closed-set structure from `ls`. The first directory level should mirror the closed set; the filename should carry the node identity.

### Why not `lca/graph_nodes/<region>/...`?

Two reasons: (1) the framework already has `lca/framework/graph/` (the runtime kernel) and `lca/framework/graph/nodes/` (the decorator + PR2 conversions); adding a third `lca/graph_nodes/` parallel to `framework/graph/` makes the layer split less clean. (2) the proposed name `lca/nodes/` is shorter and matches the existing pattern in ADR-0194 §3.3 where `lca_kernel/plugins/<region>/...` was the original cognitive-phase plugin layout (now retired; this note re-introduces the pattern at a different layer).

### Why not keep `lca/plugins/<region>/` (per-region plugin directories)?

`lca/plugins/` is the L4 plugin layer; it groups by capability (`plugins/think/` has pipeline providers, role profile providers, etc., not just nodes). Moving nodes out of `lca/plugins/<capability>/` makes the boundary between "node" (graph-typed-boundary primitive) and "provider" (capability-typed-boundary primitive) explicit. Nodes do not register capabilities; they register under `<region>::<id>`. Providers register capabilities. The directory layout should not collapse the two.

### Why not organise by decorator type (`@graph_node/` vs `@plugin/`)?

Decorator type is an implementation choice (ADR-0227 §When to use). It is not the user-facing mental model. A reader asking "where is `think.gate`" should not have to know whether it was hand-written or `@graph_node`-decorated.

### Why not `lca/nodes/loop/graph_nodes/<role>/plugin.py` (preserve the existing `loop/graph/nodes/` depth)?

`lca/nodes/loop/` is already at the same depth as `lca/nodes/think/` — the `loop/` directory name is the region-equivalent for outer-loop graph-node-executors. Preserving the extra `graph/nodes/` path would be a one-time cost that nobody pays for; the new layout saves three directory components per node file.

## Acceptance criteria

- `ls lca/nodes/<region>/` for every region in `{perceive, think, act, remember, reflect, stop, loop}` returns either the region directory or `loop/`. All six phase regions exist as directories even when empty (mirrors the closed-set).
- `git log --follow --name-status <new-path>` for every migrated file shows the original file path as the rename source; no file is deleted-and-recreated.
- `git grep "from lca.plugins.think.shortcut\|from lca.plugins.think.gate\|from lca.plugins.think.route\|from lca.plugins.think.reason"` returns zero matches after the migration. The same for `from lca.framework.graph.nodes.history_assemble\|from lca.framework.graph.nodes.llm_dispatch\|from lca.framework.graph.nodes.decision_parse` (replaced with new import paths).
- `python -c "import lca.nodes.think.route.shortcut; import lca.nodes.think.gate; import lca.nodes.think.reason.plan; import lca.nodes.think.history.assemble; import lca.nodes.loop.agent.plugin"` succeeds; `pytest tests/unit/` passes without modifying any test logic (only import paths change).
- `scripts/lca-ops audit-plugin-shape` reports no plugin-shape regressions (plugin ids, descriptors, contracts unchanged).
- `scripts/lca-ops plan validate` for each `bundles/*.yaml` succeeds (bundles reference plugins by id, not by import path).

## Risks

- **Import-path drift.** A second wave of nodes added after this PR lands in the old locations (`lca/plugins/think/<new_node>/__init__.py`) and re-introduces the split. Mitigation: enforce via `scripts/lca-ops audit-plugin-shape` or a new lint check (out of scope for this PR; tracked as follow-up).
- **Sub-group naming bikeshed.** "What is the sub-group for `think.history.assemble`?" — `history/`? `session/`? `prompt/`? The proposed layout picks `history/` (matches the node's `id="history.derive"` and `think.history.assemble` naming); if a future maintainer disagrees, the rename is a single `git mv`.
- **Loop-region ambiguity.** Is `lca/nodes/loop/` a "region" or a "graph layer"? The proposal treats it as region-equivalent (sibling to `think/`), but `loop/` is not in the six-phase closed set. A reader who greps for `region=loop` in `@graph_node(...)` invocations will find nothing — and that is correct, because loop's nodes do not use `@graph_node`; they implement `NodeExecutor` directly. The naming overlap is intentional (it surfaces the sibling relationship) and the directory README at `lca/nodes/README.md` documents the distinction.

## Migration plan

| Order | From | To | Touches |
|---|---|---|---|
| 1 | `lca/framework/graph/nodes/history_assemble.py` | `lca/nodes/think/history/assemble.py` | tests, runtime/run_session_writer.py docstring |
| 2 | `lca/framework/graph/nodes/llm_dispatch.py` | `lca/nodes/think/dispatch/llm.py` | tests |
| 3 | `lca/framework/graph/nodes/decision_parse.py` | `lca/nodes/think/decision/parse.py` | tests |
| 4 | `lca/plugins/think/shortcut.py` | `lca/nodes/think/route/shortcut.py` | tests |
| 5 | `lca/plugins/think/route.py` | `lca/nodes/think/route/route.py` | tests |
| 6 | `lca/plugins/think/reason/plan.py` | `lca/nodes/think/reason/plan.py` | tests |
| 7 | `lca/plugins/think/reason/render.py` | `lca/nodes/think/reason/render.py` | tests |
| 8 | `lca/plugins/think/gate.py` | `lca/nodes/think/gate.py` | tests |
| 9 | `lca/plugins/loop/graph/nodes/agent/plugin.py` | `lca/nodes/loop/agent/plugin.py` | tests/support/graph_node_executors.py |
| 10 | `lca/plugins/loop/graph/nodes/aggregator/plugin.py` | `lca/nodes/loop/aggregator/plugin.py` | tests/support/graph_node_executors.py |
| 11 | `lca/plugins/loop/graph/nodes/topology/plugin.py` | `lca/nodes/loop/topology/plugin.py` | tests/support/graph_node_executors.py |
| 12 | `lca/plugins/loop/graph/nodes/registry/plugin.py` | `lca/nodes/loop/registry/plugin.py` | tests/support/graph_node_executors.py |
| 13 | `lca/plugins/think/history_assemble/__init__.py` | `lca/nodes/think/history/__init__.py` (re-export shim deleted) | `lca/plugins/think/__init__.py` cleanup |
| 14 | `lca/plugins/think/llm_dispatch/__init__.py` | `lca/nodes/think/dispatch/__init__.py` (re-export shim deleted) | (same) |
| 15 | `lca/plugins/think/decision_parse/__init__.py` | `lca/nodes/think/decision/__init__.py` (re-export shim deleted) | (same) |

Steps 1-3 are the PR2 conversions that landed via `@graph_node` and now move to their final homes. Steps 4-8 are the still-handwritten `@plugin` nodes that move to the same layout (they keep their hand-written shape until a future PR converts them to `@graph_node`). Steps 9-12 are loop's graph-node-executors. Steps 13-15 delete the per-node re-export shim packages under `lca/plugins/think/` (each is a single `from lca.framework.graph.nodes.X import X` line).

After migration, `lca/plugins/think/__init__.py` no longer re-exports node objects — it re-exports pipeline providers, role profile providers, etc., only. The `lca/plugins/think/` directory retains its `cognitive/`, `composition/`, `null/`, `reasoner/`, `system/`, and `loop/` sub-packages (those are providers, not nodes).

Verification commands (run in this order):

```bash
# 1. imports resolve
python -c "import lca.nodes.think.history.assemble; import lca.nodes.think.dispatch.llm; import lca.nodes.think.decision.parse; import lca.nodes.think.route.shortcut; import lca.nodes.think.route.route; import lca.nodes.think.reason.plan; import lca.nodes.think.reason.render; import lca.nodes.think.gate; import lca.nodes.loop.agent.plugin; import lca.nodes.loop.aggregator.plugin; import lca.nodes.loop.topology.plugin; import lca.nodes.loop.registry.plugin"

# 2. plugins still discoverable by id (bundles do not change)
scripts/lca-ops audit-plugin-shape

# 3. DAG still compiles
scripts/lca-ops plan validate bundles/think.yaml
scripts/lca-ops plan validate bundles/base.yaml

# 4. existing tests pass with only import-path updates
ruff check
ruff format --check
pytest tests/unit -q
```

## Related

- ADR-0227 (the `@graph_node` DSL — this note's `@graph_node`-decorated nodes move to the new tree; ADR-0227 §Decision §1 API is unchanged)
- ADR-0194 (cognitive loop architecture convergence — defines the six-phase closed set that `region` mirrors)
- ADR-0226 (session write path — defers `RunSessionWriter` plugin slot to PR3, expressed via `@graph_node(inputs=("state", "writer"))`; not affected by this note)
- `docs/superpowers/plans/2026-09-15-pr3-graph-node-dsl.md` (PR3 implementation plan; tasks 2-3 (history_assemble / llm_dispatch / decision_parse conversions) feed into steps 1-3 above)
- `docs/design/naming-constitution.md` (the `phase_*` → `phase_graph/` merge proposal; this note extends that work to the node layout specifically)
