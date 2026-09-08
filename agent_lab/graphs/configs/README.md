# agent_lab/graphs/configs/ — Layered graph configurations

YAML files, one executable kind (`InfoEdgeSpec`), one runner. Read them
top-to-bottom as layers; each layer only references the layer below it
through an explicit `sub_spec` mount or a `kind: project` cross-spec edge.

## The layers

```
┌────────────────────────────────────────────────────────────────────────────┐
│  L1  agent_loop.yaml         — five cognitive phase hosts                  │
│      owns: perceive, think, act, reflect, remember                         │
│      stop = control_slots on remember (stop_decide / stop_focus)           │
│      delegates to:  perceive (mounts model_eye) / act / think / …          │
└────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  L2  act.yaml                — Decision → Observation                      │
│      chain: shape → authorize → execute → observe                          │
│      cross-spec:  observe.observation  ─project─►  model_eye.see.observation│
└────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  L3  model_eye.yaml (child of perceive) — frozen ContextManifest           │
│      see → guard → shape → freeze                                          │
│      cross-spec:  receives the project edge from act (above)               │
└────────────────────────────────────────────────────────────────────────────┘
```

Phase siblings at L2:
`perceive.yaml` (`resolve → sense/memory/policy → trim → commit → eye`),
`think.yaml`, `act.yaml`,
`reflect.yaml` (`join → critique → extract`),
`remember.yaml` (`admit → commit → snapshot`). Stop lives under
`control/stop_decide.yaml` + `control/stop_focus.yaml`, attached on remember.

## Per-file layout (every file follows the same 4-section shape)

```
# ============ SPEC ============       ← top file header: layer, ID, what it owns
SPEC:    id / version / region / description
GRAPH:   graph: { id, layer, purpose, members, references, relations, capabilities }
NODES:   each node has a one-line role comment + factory + config + ins/outs
EDGES:   grouped by destination node, top-to-bottom in the same order as data flow
         ┐ cross-spec edges: only declared in the file that OWNS the projection
         ┘
SUBSPECS: only on agent_loop / perceive; centralizes nested mounts
```

## Direction of references

- **Downward (spec → sub-spec)**: only via `sub_specs:` in the parent.
- **Sideways (spec ↔ sibling spec)**: only via `kind: project` cross-spec edges.
  The act→model_eye observation projection is owned by `act.yaml`.
- **Upward (parent → child)**: never. Children never know who mounted them.

## How to read the call chain for one loop turn

1. Start at `agent_loop.yaml` → `sub_specs:` to see which nested graphs mount.
2. For each mounted sub-graph, open its YAML; follow `EDGES` top-to-bottom.
3. The terminal `kind: project` edge (act → model_eye) is the C1/C2 closure
   that wires the effect layer back into the next think turn.

## Self-describe

```bash
python -m agent_lab.run --describe
python -m agent_lab.run --describe --target node:act.execute
python -m agent_lab.run --describe --target graph:act
```
