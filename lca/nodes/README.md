# `lca/nodes/` — Graph Node Implementations

Single tree for every graph node implementation in the LCA runtime.
Node files here are the typed-boundary primitives of the cognitive
six-phase closed set (ADR-0194 / ADR-0227) plus the outer-loop
graph-node-executors.

## Layout

```
lca/nodes/
├── think/                # region = "think" (closed-set phase)
│   ├── history/          # sub-group: session-history assembly
│   │   └── assemble.py   # id="history.derive" → think::history.derive
│   ├── dispatch/         # sub-group: LLM I/O
│   │   └── llm.py        # id="llm.dispatch"   → think::llm.dispatch
│   ├── decision/         # sub-group: decision-shape projection
│   │   └── parse.py      # id="decision.parse"  → think::decision.parse
│   ├── route/            # sub-group: graph access (shortcut + skill route)
│   │   ├── shortcut.py   # id="think.shortcut"  → think::think.shortcut
│   │   └── route.py      # id="think.route"     → think::think.route
│   ├── reason/           # sub-group: LLM-backed reasoning
│   │   ├── plan.py       # id="think.reason.plan"   → think::think.reason.plan
│   │   └── render.py     # id="think.reason.render" → think::think.reason.render
│   └── gate.py           # single-node sub-group: think.gate
├── loop/                 # outer-loop graph_node_executors (NOT a six-phase region)
│   ├── agent/plugin.py   # NodeType.AGENT
│   ├── aggregator/plugin.py
│   ├── topology/plugin.py
│   └── registry/plugin.py
├── perceive/             # reserved for six-phase nodes (empty today)
├── act/                  # reserved
├── remember/             # reserved
├── reflect/              # reserved
└── stop/                 # reserved
```

## Rules

1. **Region is the first directory level.** `lca/nodes/<region>/<sub-group>/<node>.py`
   for nodes that cluster; `lca/nodes/<region>/<node>.py` for single-node
   sub-groups (`think/gate.py`).
2. **All six phase regions exist as directories.** Even when empty, the
   directory tree mirrors the six-phase closed set `{perceive, think, act,
   remember, reflect, stop}`. A new phase node always has a home.
3. **`loop/` is region-equivalent for outer-loop graph-node-executors.**
   The four roles (`agent` / `aggregator` / `topology` / `registry`) do not
   appear in the six-phase closed set; they implement `NodeExecutor` for
   the outer runtime loop. They are siblings to `think/`, not children.
4. **Plugin id and composite key are unchanged.** The bundler
   (`bundles/*.yaml:plugins:`) discovers nodes by id, not by import path.
   Only the Python import path changes; `phase.think.shortcut` and
   `think::think.shortcut` continue to be the discovery keys.
5. **`@graph_node` decorator lives at `lca.framework.graph.nodes.decorator`.**
   The decorator is a graph-kernel primitive; nodes import it across the
   `lca.framework` / `lca.nodes` seam (framework is a free top-level package,
   not in the lint-imports 8-layer contract).

## Adding a new node

1. Decide the region (one of the six phases, or `loop/` for outer-loop executors).
2. Decide whether the node clusters with existing siblings (sub-group) or
   stands alone (file directly under `<region>/`).
3. Pick the implementation mechanism:
   - **Hand-written `@plugin(...)` carrier** when `node_execute` reads
     multiple capabilities from runtime, has type assertions, or branches
     on capability-presence (e.g. `think/route/shortcut.py` — capability
     absence falls through to next node).
   - **`@graph_node(...)` decorator** when the function is a typed-boundary
     adapter from `inputs=...` ports to `outputs=...` ports (e.g.
     `think/history/assemble.py`). See ADR-0227 §Decision §1 for the API.
4. Place the file at `lca/nodes/<region>/<sub-group>/<node>.py`.
5. Register it in `bundles/<bundle>.yaml:plugins:` with the existing
   `phase.<region>.<id>` plugin id (unchanged) and the new
   `$module: lca.nodes.<region>.<sub-group>.<node>` import path.
6. The plugin id ↔ module path pair is the only thing the bundler cares about.
   `bundles/concept/<node>.yaml` does not change.

## History

This tree was introduced in note
[`2026-09-15-unified-nodes-directory-layout`](../notes/implemented/seam/2026-09-15-unified-nodes-directory-layout.md)
after PR3 (`@graph_node` DSL, ADR-0227) introduced the typed-boundary
mechanism but left the node files scattered across
`lca/framework/graph/nodes/`, `lca/plugins/think/`, and
`lca/plugins/loop/graph/nodes/`. The unified tree gives every node a
home discoverable by `ls` without reading docs.
