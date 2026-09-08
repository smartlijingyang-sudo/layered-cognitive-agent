# agent_lab/graphs/configs/ — Layered graph configurations

Three YAML files, one executable kind (`InfoEdgeSpec`), one runner. Read them
top-to-bottom as three layers; each layer only references the layer below it
through an explicit `sub_spec` mount or a `kind: project` cross-spec edge.

## The three layers

```
┌────────────────────────────────────────────────────────────────────────────┐
│  L1  agent_loop.yaml         — six-phase skeleton                          │
│      owns: perceive, think, act, reflect, remember, stop (5 stubs + 2     │
│            sub_spec hosts + 2 local workers flatten_manifest/call_llm_node) │
│      delegates to:  mv_assemble        (via sub_spec on assemble_for_think)│
│                     effect_dispatch    (via sub_spec on act)                │
└────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  L2  effect_dispatch.yaml    — one tool call, end-to-end                   │
│      chain: build_intent → grant_check → route_verdict → dispatch →        │
│             write_receipt → integrate                                     │
│      delegates to:  (no sub_specs; provider is loaded per-node)            │
│      cross-spec:  integrate.observation  ─project─►  mv_assemble.classify. │
│                  results  (C1/C2 closure)                                  │
└────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  L3  mv_assemble.yaml        — frozen ContextManifest for the LLM          │
│      left branch:  classify → dedupe → rank → redact                       │
│      right bypass: system / history go straight to merge                   │
│      merge:        order [system, sanitized, history] → messages           │
│      fan-out:      messages → {validate, commit, assemble_lca}             │
│      delegates to:  (no sub_specs; assemble_lca is a single node)          │
│      cross-spec:  receives the project edge from effect_dispatch (above)   │
└────────────────────────────────────────────────────────────────────────────┘
```

## Per-file layout (every file follows the same 4-section shape)

```
# ============ SPEC ============       ← top file header: layer, ID, what it owns
SPEC:    id / version / region / description
GRAPH:   graph: { id, layer, purpose, members, references, relations, capabilities }
NODES:   each node has a one-line role comment + factory + config + ins/outs
EDGES:   grouped by destination node, top-to-bottom in the same order as data flow
         ┐ cross-spec edges: only declared in the file that OWNS the projection
         ┘
SUBSPECS: only on agent_loop; centralizes where nested graphs are mounted
MV_FEED:  only on agent_loop; tells consumers which sub-graph produced the manifest
```

## Direction of references

- **Downward (spec → sub-spec)**: only via `sub_specs:` in the parent. A parent
  may not list child nodes.
- **Sideways (spec ↔ sibling spec)**: only via `kind: project` cross-spec edges.
  The effect-layer projection into the model-visible layer is owned by the
  effect layer (declared in `effect_dispatch.yaml`), not by the root or by
  `mv_assemble.yaml`.
- **Upward (parent → child)**: never. Children never know who mounted them.
- **Initial inputs (`_initial` port)**: only the root spec's initial ports are
  public; child specs receive their inputs through the parent's `sub_specs[*].input_map`.

## What lives in node.config (and what doesn't)

`node.config` is a free dict that the node's `execute()` reads at call time.
Two patterns are first-class:

1. **Port renames** — `from` / `to` to alias the default port names.
2. **Provider selection** — `provider_kind` (shorthand) or `provider_ref`
   (`module:Class`); `provider_config` is opaque kwargs to the provider.
   See `agent_lab/nodes/llm.py` and `nodes/tool.py` for the resolution order.

Everything else (e.g. `tool: echo`, `allow: [echo, calc]`, `keep: 50`) is
node-specific and stays in that node's `config` block.

## How to read the call chain for one loop turn

1. Start at `agent_loop.yaml` → `sub_specs:` to see which nested graphs mount.
2. For each mounted sub-graph, open its own YAML; start at the same
   `# ============ SPEC ============` header to confirm the spec ID and
   the cross-spec edges it owns.
3. Follow `EDGES` top-to-bottom; they read in the same order as the data path.
4. The terminal `kind: project` edge (only one in the whole system) is the
   C1/C2 closure that wires the effect layer back into the next think turn.

## Self-describe

```bash
python -m agent_lab.run --describe                    # all nodes + graphs
python -m agent_lab.run --describe --target node:call_llm
python -m agent_lab.run --describe --target graph:agent_loop
```
