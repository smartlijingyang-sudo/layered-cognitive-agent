# Agent Lab Graph-Node Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `agent_lab` graph composition a compile-time contract: workers stay tiny, control is sibling hosts declared in YAML, Kernel seams are injected, plugin hooks cannot rewrite topology or artifacts.

**Architecture:** One executable kind (`InfoEdgeSpec`). Hosts are `graph.call` (exactly one `sub_spec`). Data moves only on typed edges. Cross-spec reads are `borrow`+Grant or parent `input_map`. Observation hooks are contained and read-only. Kernel (Compile / Interpreter / `Session.append` / SafeExecutor) stays a closed set, not a graph.

**Tech Stack:** Python 3.12, Pydantic frozen models, pytest, existing `agent_lab.graph.validate` / `compile` / `runtime.runner`, YAML graphs under `agent_lab/graphs/configs/`.

**Spec:** [docs/notes/proposed/primitive/2026-09-09-agent-lab-graph-node-composition.md](../proposed/primitive/2026-09-09-agent-lab-graph-node-composition.md)

## Global Constraints

- Do not graphify Kernel. Do not add a compose-graph or `slots:` sugar.
- Do not Cordis-`@plugin` each `@node` worker ([absorb-end-state](../proposed/seam/2026-09-08-agent-lab-absorb-end-state.md)).
- Session single-track and Body assembly belong to [ADR-0209](../../adr/0209-agent-lab-cordis-unification.md); this plan only injects declared seams, it does not invent a second Session.
- Same change must not keep plugin insertion and claim parent YAML is SSOT.
- COMPAT shims deleted in the same commit that introduces them.
- Tests are process-local: unique factory names, `try/finally` around registry fixtures, no shared `traces/` paths.
- `lint-imports` / full mypy / layering failures that already exist stay labeled pre-existing; only new failures block a task.
- Promote the Note to `implemented/` only after Task 14 delete-when holds.

---

## File map

| File | Responsibility |
|---|---|
| `agent_lab/nodes/host/graph_call/plugin.py` | No-op host factory after subgraph export |
| `agent_lab/nodes/host/__init__.py` | Register `graph.call` |
| `agent_lab/nodes/__init__.py` | Import `host` package |
| `agent_lab/graph/validate.py` | N1–N8, C4 borrow+Grant, C1 reachability |
| `agent_lab/graph/spec.py` | `Edge.grant_id` optional |
| `agent_lab/primitives/edge.py` | `grant_id: str \| None = None` |
| `agent_lab/graph/compile.py` | Reject topology rewrite from `before_compile`; stop swallowing hook errors |
| `agent_lab/graphs/loader.py` | `load_closure(root_id)` follows `sub_specs` |
| `agent_lab/graphs/configs/agent_loop.yaml` | Sibling control hosts + edges; drop `control_slots` plugin |
| `agent_lab/graphs/configs/perceive.yaml` | `eye` factory `graph.call` |
| `agent_lab/plugins/control_slots.py` | Delete |
| `agent_lab/plugins/semantic_router.py` | Delete rewrite path (file delete) |
| `agent_lab/plugins/parsers.py` `observation.py` `memory_extract.py` `tool_guard.py` | Delete as business-plane hooks once workers own the logic |
| `agent_lab/nodes/base.py` | `execute(..., seams=None)` + `invoke` passes seams |
| `agent_lab/runtime/seams.py` | `KERNEL_SEAM_IDS` + `SeamMap` |
| `agent_lab/runtime/runner.py` | Invoke-then-route; atomic `output_map`; no output-mutating hooks |
| `agent_lab/graphs/configs/act.yaml` | Split execute into route + body + receipt workers |
| `agent_lab/nodes/act/body/plugin.py` | Allow-path Body.act only |
| `agent_lab/nodes/act/receipt_denied/plugin.py` | Deny receipt |
| `agent_lab/nodes/act/receipt_none/plugin.py` | Skip / no_effect receipt |
| `tests/agent_lab/test_validate_composition.py` | Negative compile canaries for N* |
| `tests/agent_lab/test_skeleton_no_business.py` | Invert plugin-insertion assertions |
| `tests/agent_lab/test_stop_subgraph.py` | Stop is a sibling host, not `before_compile` mutation |
| `tests/agent_lab/test_error_routing.py` | Route after invoke |
| `scripts/check_agent_lab_node_imports.py` | N7: worker `plugin.py` must not import sibling workers |

---

### Task 1: `graph.call` host factory (N4)

**Files:**
- Create: `agent_lab/nodes/host/graph_call/plugin.py`
- Create: `agent_lab/nodes/host/__init__.py`
- Modify: `agent_lab/nodes/__init__.py` (import `host`)
- Modify: `agent_lab/graph/validate.py` (N4)
- Modify: `agent_lab/graphs/configs/agent_loop.yaml` (five phase hosts `factory: graph.call`)
- Modify: `agent_lab/graphs/configs/perceive.yaml` (`eye` `factory: graph.call`)
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: `Node.execute(node, inputs) -> dict[str, Artifact]` (pre-seams)
- Produces: factory name `"graph.call"`; N4 error string prefix `"N4:"`

- [ ] **Step 1: Write the failing tests**

```python
# tests/agent_lab/test_validate_composition.py
from agent_lab.graph.spec import InfoEdgeSpec, InfoNode, SubSpecLink
from agent_lab.graph.validate import validate
from agent_lab.primitives.edge import Edge
from agent_lab.primitives.port import PortRef


def _edge(eid: str, spec: str, frm: tuple[str, str], to: tuple[str, str]) -> Edge:
    return Edge(
        id=eid,
        from_ref=PortRef(spec_id=spec, node_id=frm[0], port_id=frm[1]),
        to_ref=PortRef(spec_id=spec, node_id=to[0], port_id=to[1]),
    )


def test_n4_rejects_identity_host() -> None:
    spec = InfoEdgeSpec(
        id="t",
        nodes=[
            InfoNode(
                id="think",
                factory="identity",
                ins=["in"],
                outs=["out"],
            )
        ],
        sub_specs=[
            SubSpecLink(node_id="think", sub_spec_id="think_inner", input_map={"in": "in"}, output_map={"out": "out"})
        ],
    )
    errs = validate(spec)
    assert any(e.startswith("N4:") and "think" in e for e in errs)


def test_n4_accepts_graph_call_host() -> None:
    spec = InfoEdgeSpec(
        id="t",
        nodes=[InfoNode(id="think", factory="graph.call", ins=["in"], outs=["out"])],
        sub_specs=[
            SubSpecLink(node_id="think", sub_spec_id="think_inner", input_map={"in": "in"}, output_map={"out": "out"})
        ],
    )
    errs = validate(spec)
    assert not any(e.startswith("N4:") for e in errs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_n4_rejects_identity_host tests/agent_lab/test_validate_composition.py::test_n4_accepts_graph_call_host -v`

Expected: FAIL — `graph.call` unregistered and/or no `N4:` errors.

- [ ] **Step 3: Implement `graph.call` and N4**

`agent_lab/nodes/host/graph_call/plugin.py`:

```python
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="graph.call",
    layer=NodeLayer.PHASE,
    kind=NodeKind.PASSTHROUGH,
    description="Host for exactly one nested InfoEdgeSpec. execute copies subgraph exports already written onto host ports.",
    inputs=[],
    outputs=[],
)
class GraphCall(Node):
    name = "graph.call"

    def execute(self, node, inputs):
        empty = Artifact(kind=ArtifactKind.TEXT, content="")
        return {port: inputs.get(port, empty) for port in node.outs}
```

`nodes/host/__init__.py`: import the plugin. `nodes/__init__.py`: `from agent_lab.nodes import host  # noqa: F401`.

In `validate()` after the existing sub_spec loop:

```python
for link in spec.sub_specs:
    host = spec.node(link.node_id)
    if host.factory != "graph.call":
        errs.append(
            f"N4: host {host.id} factory={host.factory!r} must be 'graph.call'"
        )
```

Change the six YAML hosts (`agent_loop` perceive/think/act/reflect/remember, `perceive.eye`) from `factory: identity` to `factory: graph.call`. Leave their `ins`/`outs` unchanged.

- [ ] **Step 4: Run tests + existing graph compile**

Run:

```bash
uv run pytest tests/agent_lab/test_validate_composition.py::test_n4_rejects_identity_host \
  tests/agent_lab/test_validate_composition.py::test_n4_accepts_graph_call_host \
  tests/agent_lab/test_think_subgraph.py tests/agent_lab/test_perceive_subgraph.py \
  tests/agent_lab/test_act_subgraph.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/nodes/host agent_lab/nodes/__init__.py agent_lab/graph/validate.py \
  agent_lab/graphs/configs/agent_loop.yaml agent_lab/graphs/configs/perceive.yaml \
  tests/agent_lab/test_validate_composition.py
git commit -m "feat(lab): add graph.call host factory and N4"
```

---

### Task 2: N1 YAML ports ⊆ manifest (workers only)

**Files:**
- Modify: `agent_lab/graph/validate.py`
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: `NodeRegistry.describe(factory) -> NodeManifest` with `.inputs` / `.outputs` `PortInfo.id`
- Produces: `"N1:"` errors; `graph.call` and unknown factories skipped (unknown already fails at runtime)

- [ ] **Step 1: Write the failing test**

```python
def test_n1_rejects_undeclared_worker_port() -> None:
    spec = InfoEdgeSpec(
        id="t",
        nodes=[InfoNode(id="expose", factory="think.expose", ins=["no_such_port"], outs=["messages"])],
    )
    errs = validate(spec)
    assert any(e.startswith("N1:") and "no_such_port" in e for e in errs)


def test_n1_skips_graph_call() -> None:
    spec = InfoEdgeSpec(
        id="t",
        nodes=[InfoNode(id="think", factory="graph.call", ins=["custom"], outs=["custom"])],
    )
    errs = validate(spec)
    assert not any(e.startswith("N1:") for e in errs)
```

Need `import agent_lab.nodes  # noqa: F401` at module top so `think.expose` is registered.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_n1_rejects_undeclared_worker_port -v`

Expected: FAIL (no `N1:`).

- [ ] **Step 3: Implement N1**

```python
from agent_lab.nodes.base import NodeRegistry

_HOST_FACTORIES = frozenset({"graph.call"})

def _check_n1_ports(spec: InfoEdgeSpec) -> list[str]:
    errs: list[str] = []
    for n in spec.nodes:
        if n.factory in _HOST_FACTORIES:
            continue
        try:
            manifest = NodeRegistry.describe(n.factory)
        except KeyError:
            continue
        declared_in = {p.id for p in manifest.inputs}
        declared_out = {p.id for p in manifest.outputs}
        for port in n.ins:
            if declared_in and port not in declared_in:
                errs.append(
                    f"N1: node {n.id} ins port {port!r} not in manifest {n.factory} inputs {sorted(declared_in)}"
                )
        for port in n.outs:
            if declared_out and port not in declared_out:
                errs.append(
                    f"N1: node {n.id} outs port {port!r} not in manifest {n.factory} outputs {sorted(declared_out)}"
                )
    return errs
```

If this fails on existing graphs because YAML ports differ from manifest (e.g. `identity` `from`/`to` vs host-like names), **do not skip N1**. Fix the YAML/manifest of the offending **worker** so they match. Hosts are already `graph.call` and exempt. `identity` used as true passthrough must use `ins`/`outs` ⊆ `{from, to}` **or** extend Identity's manifest ports to the actual names and stop using `config.from`/`to` as the port table.

If a worker's YAML uses extra names only via `config.from`/`to`, rename YAML `ins`/`outs` to the manifest ids and delete the alias keys in that same commit.

- [ ] **Step 4: Run N1 tests + full agent_lab suite subset**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py tests/agent_lab/test_think_subgraph.py tests/agent_lab/test_act_subgraph.py -q`

Expected: PASS. If a real graph fails N1, fix that graph before committing.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/graph/validate.py tests/agent_lab/test_validate_composition.py agent_lab/graphs agent_lab/nodes
git commit -m "feat(lab): enforce N1 YAML ports subset of node manifest"
```

---

### Task 3: N5 cross-spec edges are `project` or `borrow`

**Files:**
- Modify: `agent_lab/graph/validate.py` (today it already errors on cross-spec non-`project`; extend to allow `borrow`)
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: `Edge.kind`, `PortRef.spec_id`
- Produces: `"N5:"` (keep existing `C1:` cross-spec message **or** rename to `N5:` in this commit and update any test that searches `C1: edge`)

- [ ] **Step 1: Write the failing tests**

```python
def test_n5_rejects_cross_spec_data() -> None:
    spec = InfoEdgeSpec(
        id="act",
        nodes=[InfoNode(id="observe", factory="act.observe", ins=["receipt"], outs=["observation"])],
        edges=[
            Edge(
                id="bad",
                from_ref=PortRef(spec_id="act", node_id="observe", port_id="observation"),
                to_ref=PortRef(spec_id="model_eye", node_id="see", port_id="observation"),
                kind=EdgeKind.DATA,
            )
        ],
    )
    errs = validate(spec)
    assert any("N5:" in e or "C1:" in e for e in errs)


def test_n5_allows_project_and_borrow() -> None:
    from agent_lab.primitives.edge import EdgeKind
    spec = InfoEdgeSpec(
        id="act",
        nodes=[InfoNode(id="observe", factory="act.observe", ins=["receipt"], outs=["observation"])],
        edges=[
            Edge(
                id="ok",
                from_ref=PortRef(spec_id="act", node_id="observe", port_id="observation"),
                to_ref=PortRef(spec_id="model_eye", node_id="see", port_id="observation"),
                kind=EdgeKind.PROJECT,
            )
        ],
    )
    errs = validate(spec)
    assert not any("cross spec" in e.lower() or e.startswith("N5:") for e in errs)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_n5_rejects_cross_spec_data tests/agent_lab/test_validate_composition.py::test_n5_allows_project_and_borrow -v`

Expected: first may already PASS (existing C1 check); second PASS. If `borrow` is still rejected, Step 3 must allow it.

- [ ] **Step 3: Allow `borrow` as the other legal cross-spec kind**

Replace the `elif cross_spec and e.kind != EdgeKind.PROJECT` branch with:

```python
elif cross_spec and e.kind not in (EdgeKind.PROJECT, EdgeKind.BORROW):
    errs.append(
        f"N5: edge {e.id} crosses spec boundary with kind={e.kind.value}; only project|borrow allowed"
    )
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py tests/agent_lab/test_act_subgraph.py -q`

Expected: PASS (`act.yaml` project edge remains legal).

- [ ] **Step 5: Commit**

```bash
git add agent_lab/graph/validate.py tests/agent_lab/test_validate_composition.py
git commit -m "feat(lab): N5 cross-spec edges only project or borrow"
```

---

### Task 4: Control as sibling hosts + N3 + delete insertion plugin

This is the SSOT cut. N3 and YAML siblings land together so `agent_loop` still compiles.

**Files:**
- Modify: `agent_lab/graphs/configs/agent_loop.yaml`
- Modify: `agent_lab/graph/validate.py` (N3)
- Modify: `agent_lab/graphs/loader.py` (`load_closure`)
- Modify: `agent_lab/run.py` (use `load_closure`)
- Modify: `agent_lab/plugins/__init__.py` (drop `ControlSlotsPlugin`)
- Modify: `agent_lab/graph/compile.py` (stop loading control yaml via plugin)
- Delete: `agent_lab/plugins/control_slots.py`
- Modify: `tests/agent_lab/test_skeleton_no_business.py`
- Modify: `tests/agent_lab/test_stop_subgraph.py`
- Modify: any test that calls `ControlSlotsPlugin.before_compile`
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: `graph.call` hosts (Task 1)
- Produces: `load_closure(root_id: str) -> dict[str, InfoEdgeSpec]`; N3 `"N3:"`; `agent_loop` nodes `stop_decide`, `stop_focus`, `think_guard`, `remember_admit`, `perceive_context` as siblings

- [ ] **Step 1: Write failing N3 + sibling tests**

```python
def test_n3_rejects_two_sub_specs_on_one_host() -> None:
    spec = InfoEdgeSpec(
        id="loop",
        nodes=[InfoNode(id="remember", factory="graph.call", ins=["in"], outs=["out"])],
        sub_specs=[
            SubSpecLink(node_id="remember", sub_spec_id="remember", input_map={"in": "in"}, output_map={"out": "out"}),
            SubSpecLink(node_id="remember", sub_spec_id="stop_decide", input_map={"in": "in"}, output_map={"out": "out"}),
        ],
    )
    errs = validate(spec)
    assert any(e.startswith("N3:") and "remember" in e for e in errs)


def test_agent_loop_yaml_declares_stop_siblings() -> None:
    from agent_lab.graphs.loader import load_spec
    from pathlib import Path
    path = Path("agent_lab/graphs/configs/agent_loop.yaml")
    spec = load_spec(path)
    ids = {n.id for n in spec.nodes}
    assert "stop_decide" in ids and "stop_focus" in ids
    assert "think_guard" in ids
    hosts = {}
    for link in spec.sub_specs:
        hosts.setdefault(link.node_id, []).append(link.sub_spec_id)
    assert hosts.get("remember") == ["remember"]
    assert hosts.get("stop_decide") == ["stop_decide"]
    assert ("remember", "stop_decide") not in {(l.node_id, l.sub_spec_id) for l in spec.sub_specs}
```

Invert `tests/agent_lab/test_skeleton_no_business.py`:

- Delete `test_compile_without_control_slots_plugin_does_not_insert`
- Delete `test_control_slots_plugin_inserts_on_before_compile`
- Add:

```python
def test_compile_without_control_slots_plugin_still_has_stop_hosts() -> None:
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.graphs.loader import load_closure
    specs = load_closure("agent_loop")
    stripped = [p for p in specs["agent_loop"].plugins if p.kind != "control_slots"]
    specs["agent_loop"] = specs["agent_loop"].model_copy(update={"plugins": stripped})
    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)
    calls = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    assert "stop_decide" in calls
    assert "think_guard" in calls
    by_host: dict[str, list[str]] = {}
    for x in bundle.subgraph_calls:
        by_host.setdefault(x["node_id"], []).append(x["sub_spec_id"])
    assert by_host["remember"] == ["remember"]
    assert by_host["stop_decide"] == ["stop_decide"]
```

Rewrite `test_agent_loop_attaches_stop_control_on_remember` to load YAML (no plugin) and assert sibling nodes + a `data` edge `remember.state_ref -> stop_decide.in_state`.

- [ ] **Step 2: Run the new tests to see them fail**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_n3_rejects_two_sub_specs_on_one_host tests/agent_lab/test_validate_composition.py::test_agent_loop_yaml_declares_stop_siblings tests/agent_lab/test_skeleton_no_business.py -v`

Expected: FAIL (YAML still has one remember host; plugin still present).

- [ ] **Step 3: Implement loader, N3, YAML, delete plugin**

`load_closure` in `loader.py`:

```python
def load_closure(root_id: str) -> dict[str, InfoEdgeSpec]:
    """Load root_id and every nested sub_spec id, recursively."""
    loaded = load_registry(root_id)
    pending = [root_id]
    seen: set[str] = {root_id}
    while pending:
        current = loaded[pending.pop()]
        for link in current.sub_specs:
            if link.sub_spec_id in seen:
                continue
            seen.add(link.sub_spec_id)
            loaded.update(load_registry(link.sub_spec_id))
            pending.append(link.sub_spec_id)
    return loaded
```

N3 in `validate()`:

```python
from collections import Counter
counts = Counter(link.node_id for link in spec.sub_specs)
for node_id, n in counts.items():
    if n != 1:
        errs.append(f"N3: host {node_id} has {n} sub_specs; exactly one allowed")
```

`agent_loop.yaml` (canonical fragment — apply equivalently for `think_guard` on think, `perceive_context` on perceive, `remember_admit` beside remember):

```yaml
  - id: remember
    region: phase:remember
    factory: graph.call
    ins: [in_reflection, in_observation, in_decision, in_candidates]
    outs: [journal_fact, state_ref, remember_signal]
  - id: stop_decide
    region: control
    factory: graph.call
    ins: [state_ref, in_decision, in_observation, in_reflection]
    outs: [stop_decision, terminal]
  - id: stop_focus
    region: control
    factory: graph.call
    ins: [state_ref, in_decision]
    outs: [focus_verdict]
```

Edges (same file, after existing remember edges):

```yaml
  - id: e_remember_state_to_stop_decide
    from: { spec: agent_loop, node: remember, port: state_ref }
    to:   { spec: agent_loop, node: stop_decide, port: state_ref }
    kind: data
  - id: e_think_dec_to_stop_decide
    from: { spec: agent_loop, node: think, port: decision_out }
    to:   { spec: agent_loop, node: stop_decide, port: in_decision }
    kind: data
  - id: e_act_obs_to_stop_decide
    from: { spec: agent_loop, node: act, port: out_observation }
    to:   { spec: agent_loop, node: stop_decide, port: in_observation }
    kind: data
  - id: e_reflect_to_stop_decide
    from: { spec: agent_loop, node: reflect, port: reflection_out }
    to:   { spec: agent_loop, node: stop_decide, port: in_reflection }
    kind: data
  - id: e_remember_state_to_stop_focus
    from: { spec: agent_loop, node: remember, port: state_ref }
    to:   { spec: agent_loop, node: stop_focus, port: state_ref }
    kind: data
  - id: e_think_dec_to_stop_focus
    from: { spec: agent_loop, node: think, port: decision_out }
    to:   { spec: agent_loop, node: stop_focus, port: in_decision }
    kind: data
```

`sub_specs` add:

```yaml
  - node: stop_decide
    sub_spec: stop_decide
    input_map:
      state_ref: in_state
      in_decision: in_decision
      in_observation: in_observation
      in_reflection: in_reflection
    output_map:
      stop_decision: stop_decision
      terminal: terminal
  - node: stop_focus
    sub_spec: stop_focus
    input_map:
      state_ref: in_state
      in_decision: in_decision
    output_map:
      focus_verdict: focus_verdict
```

Think guard: sibling `think_guard` host, edge `think.decision_out -> think_guard.in_decision`, output back if the loop consumes it. If the current plugin wrapped the same think host, **do not** double-enforce: keep `think.yaml` `guard` as SSOT and mount `think_guard` as passthrough sibling **or** drop the control graph if it is pure passthrough. Spec: control is a graph. Keep the sibling even if passthrough.

`observe_checkpoint` / `observe_wildcard`: unique node ids per phase (`perceive_observe_checkpoint`, …) each `graph.call` mounting the same spec. If a phase host has no `in_event_log` producer, omit that observer rather than inventing a fake port.

Remove from `plugins:`:

```yaml
  - id: default_control_slots
    kind: control_slots
```

Delete `agent_lab/plugins/control_slots.py`. Drop export from `plugins/__init__.py`. `rg ControlSlotsPlugin agent_lab/` must be 0.

`run.py` `load_registry(...)` → `load_closure("agent_loop")` when graph is `agent_loop`; for single-graph runs keep `load_registry` + `load_closure` of that id.

- [ ] **Step 4: Run**

```bash
uv run pytest tests/agent_lab/test_validate_composition.py tests/agent_lab/test_skeleton_no_business.py \
  tests/agent_lab/test_stop_subgraph.py tests/agent_lab/test_stop_focus_subgraph.py \
  tests/agent_lab/test_control_slot_graphs.py -q
rg "PHASE_OWNER_WIRING|ControlSlotsPlugin" agent_lab/
python -m agent_lab.run --describe --target graph:agent_loop
```

Expected: pytest PASS; `rg` empty; describe lists `stop_decide` as a node with the `state_ref` edge.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/graphs agent_lab/graph/validate.py agent_lab/graph/compile.py \
  agent_lab/plugins agent_lab/run.py tests/agent_lab
git add -u agent_lab/plugins/control_slots.py
git commit -m "feat(lab): declare control as sibling hosts; delete ControlSlotsPlugin"
```

---

### Task 5: `before_compile` must not rewrite topology

**Files:**
- Modify: `agent_lab/graph/compile.py`
- Modify: `tests/agent_lab/test_plugins.py` (`test_compile_hook_before_compile_fires_in_order` may stay if hooks return the same spec)
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: `GraphPlugin.before_compile(spec, sub_registry) -> spec`
- Produces: `ValidationError` containing `"topology rewrite"`

- [ ] **Step 1: Failing test**

```python
def test_before_compile_topology_rewrite_fails(monkeypatch) -> None:
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.graph.validate import ValidationError
    from agent_lab.plugins.base import GraphPlugin

    class _Mutator(GraphPlugin):
        def before_compile(self, spec, sub_registry=None):
            extra = InfoNode(id="sneak", factory="identity", ins=[], outs=["x"])
            return spec.model_copy(update={"nodes": [*spec.nodes, extra]})

    monkeypatch.setattr(
        "agent_lab.graph.compile._resolve_plugins",
        lambda spec: [_Mutator(name="__mut__", kind="event_sink")],
    )
    spec = InfoEdgeSpec(
        id="t",
        nodes=[InfoNode(id="a", factory="identity", ins=[], outs=["x"])],
    )
    try:
        compile_spec(spec, sub_registry={})
        raised = False
    except ValidationError:
        raised = True
    assert raised
```

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_before_compile_topology_rewrite_fails -v`

Expected: FAIL (`compile` currently accepts rewrite).

- [ ] **Step 3: Implement**

In `compile()` after each `before_compile`:

```python
rewritten = plugin.before_compile(spec, sub_registry)
if rewritten is None:
    continue
if _topology_signature(rewritten) != _topology_signature(spec):
    raise ValidationError(
        [f"plugin {plugin.name} before_compile rewrote topology; forbidden"]
    )
spec = rewritten  # metadata-only copies still allowed
```

```python
def _topology_signature(spec: InfoEdgeSpec) -> str:
    return _stable_hash({
        "nodes": [(n.id, n.factory, n.ins, n.outs) for n in spec.nodes],
        "edges": [e.model_dump() for e in spec.edges],
        "sub_specs": [s.model_dump() for s in spec.sub_specs],
        "grants": [g.model_dump() for g in spec.grants],
    })
```

Remove the `except Exception: log.warning` around `before_compile` — hook failures fail compile.

Returning the identical spec (recorders in `test_plugins.py`) still works.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_before_compile_topology_rewrite_fails tests/agent_lab/test_plugins.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/graph/compile.py tests/agent_lab/test_validate_composition.py tests/agent_lab/test_plugins.py
git commit -m "feat(lab): reject before_compile topology rewrites"
```

---

### Task 6: Observation hooks must not rewrite outputs (N6)

**Files:**
- Modify: `agent_lab/runtime/runner.py` (`_apply_output_hooks` must not replace artifacts)
- Delete: `agent_lab/plugins/semantic_router.py`
- Modify: `agent_lab/plugins/__init__.py`, `agent_loop.yaml` plugins list
- Modify: `tests/agent_lab/test_skeleton_no_business.py` (delete `test_semantic_router_plugin_fans_out_on_schema_ref`)
- Modify: `tests/agent_lab/test_business_logic_plugins.py` (move parse/observe/extract assertions onto worker tests if they only passed via hooks)
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: worker outputs as the data plane
- Produces: observers may log; `outputs` identity-equal after hooks

- [ ] **Step 1: Failing test**

```python
def test_n6_runner_does_not_let_hooks_replace_outputs() -> None:
    from agent_lab.graph.spec import InfoNode, InfoEdgeSpec
    from agent_lab.runtime.runner import run as run_graph
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    spec = InfoEdgeSpec(
        id="t",
        nodes=[InfoNode(id="a", factory="identity", config={"from": "from", "to": "to"}, ins=["from"], outs=["to"])],
        edges=[
            Edge(
                id="e",
                from_ref=PortRef(spec_id="t", node_id="_initial", port_id="from"),
                to_ref=PortRef(spec_id="t", node_id="a", port_id="from"),
            )
        ],
    )
    src = Artifact(kind=ArtifactKind.TEXT, content="keep", schema_ref="decision.v1")
    trace = run_graph(spec, initial={"from": src}, sub_registry={})
    assert trace.final_artifacts["to"].content == "keep"
```

And a unit test that a plugin attempting to swap `payload["outputs"]` is ignored — implement by making `_apply_output_hooks` copy outputs only if `id(new) == id(old)` per port, else keep original and log.

- [ ] **Step 2: Run to fail if router still mutates**

Run: `uv run pytest tests/agent_lab/test_skeleton_no_business.py::test_semantic_router_plugin_fans_out_on_schema_ref -v`

This test currently **passes** by requiring mutation. Rewrite it to assert the opposite, then watch it fail until the router is gone.

- [ ] **Step 3: Delete semantic_router; freeze outputs in runner**

`_apply_output_hooks`: after `fanout_hooks`, **do not** assign `ctx.payload["outputs"]` back onto the node outputs. Hooks may read. Drop `semantic_router` from YAML and package exports.

Parse/observe/extract/tool_guard: if `tests/agent_lab/test_business_logic_plugins.py` fails because classify/observe/extract no longer get hook rewriting, add the missing branch to the existing worker (`think.classify`, `act.observe`, `reflect.extract`, `act.authorize`) in **this** commit — that is the worker owning the logic, not a new plugin.

- [ ] **Step 4: Run**

```bash
uv run pytest tests/agent_lab/test_skeleton_no_business.py tests/agent_lab/test_business_logic_plugins.py \
  tests/agent_lab/test_think_subgraph.py tests/agent_lab/test_act_subgraph.py -q
rg semantic_router agent_lab/
```

Expected: PASS; `rg` empty (or only comments in this plan/note).

- [ ] **Step 5: Commit**

```bash
git add -u agent_lab/plugins agent_lab/runtime/runner.py agent_lab/graphs/configs/agent_loop.yaml tests/agent_lab
git commit -m "feat(lab): observation hooks read-only; remove semantic_router"
```

---

### Task 7: `execute(node, inputs, seams)` + kernel seam map

**Files:**
- Create: `agent_lab/runtime/seams.py`
- Modify: `agent_lab/nodes/base.py` (`Node.execute`, `invoke`)
- Modify: `agent_lab/runtime/runner.py` (pass seams into `invoke_node`)
- Modify: every `def execute(self, node, inputs)` under `agent_lab/nodes/` and `tests/agent_lab/test_error_routing.py` to `def execute(self, node, inputs, seams=None)`
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: none
- Produces:

```python
# agent_lab/runtime/seams.py
from collections.abc import Mapping
from typing import Any

SeamMap = Mapping[str, Any]

KERNEL_SEAM_IDS: frozenset[str] = frozenset({
    "session.append",
    "safe_executor",
    "tool_registry",
    "llm_call",
    "decision_gate",
    "stop_policy",
})
```

```python
def invoke(
    node: InfoNode,
    inputs: dict[str, Artifact],
    seams: SeamMap | None = None,
) -> dict[str, Artifact]:
    factory = NodeRegistry.get(node.factory)
    return factory().execute(node, inputs, seams)
```

- [ ] **Step 1: Failing test**

```python
def test_invoke_passes_seams() -> None:
    from agent_lab.nodes.base import Node, invoke, register
    from agent_lab.graph.spec import InfoNode
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    seen: dict[str, object] = {}

    @register
    class _SeamProbe(Node):
        name = "_seam_probe"
        def execute(self, node, inputs, seams=None):
            seen["seams"] = seams
            return {"out": Artifact(kind=ArtifactKind.TEXT, content="ok")}

    n = InfoNode(id="p", factory="_seam_probe", ins=[], outs=["out"])
    invoke(n, {}, seams={"tool_registry": "R"})
    assert seen["seams"] == {"tool_registry": "R"}
```

Un-register in `finally` if `register` forbids duplicates across tests — use a unique name `_seam_probe_task7`.

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_invoke_passes_seams -v`

Expected: FAIL (`execute() takes 3 positional arguments but 4 were given` or seams dropped).

- [ ] **Step 3: Change signature everywhere**

```bash
rg -l "def execute\(self, node, inputs\)" agent_lab/nodes tests/agent_lab
```

Every hit becomes `def execute(self, node, inputs, seams=None)`. Base class:

```python
def execute(
    self,
    node: InfoNode,
    inputs: dict[str, Artifact],
    seams: Mapping[str, object] | None = None,
) -> dict[str, Artifact]:
    raise NotImplementedError
```

Runner:

```python
from agent_lab.runtime.seams import SeamMap
# _Runner stores self.seams: SeamMap
outputs = invoke_node(node, inputs, self.seams)
```

Do **not** wire `lab_tools()` into seams yet (Task 8/10). Empty `{}` is enough for this task.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/agent_lab -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/nodes/base.py agent_lab/runtime/seams.py agent_lab/runtime/runner.py \
  agent_lab/nodes tests/agent_lab
git commit -m "feat(lab): pass declared seams into node execute"
```

---

### Task 8: N2 `requires` must be provided

**Files:**
- Modify: `agent_lab/graph/validate.py`
- Modify: `agent_lab/runtime/runner.py` (build seams from `KERNEL_SEAM_IDS` ∩ union of worker requires; missing declared seam at invoke → `_NonRetryableError`)
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: `NodeManifest.requires`, `NodeManifest.provides`, `KERNEL_SEAM_IDS`
- Produces: `"N2:"` compile errors

- [ ] **Step 1: Failing test**

```python
def test_n2_rejects_unknown_require() -> None:
    spec = InfoEdgeSpec(
        id="t",
        nodes=[InfoNode(id="g", factory="think.guard", ins=["decision"], outs=["enforced_decision"])],
    )
    # think.guard requires decision_gate — allowed via KERNEL_SEAM_IDS.
    # Use a throwaway factory in this test after registering a node with requires=["nope"].
```

Register `_need_nope` with `@node(..., requires=["not_a_seam"])` in the test module, then:

```python
    spec = InfoEdgeSpec(id="t", nodes=[InfoNode(id="x", factory="_need_nope", ins=[], outs=["o"])])
    errs = validate(spec)
    assert any(e.startswith("N2:") and "not_a_seam" in e for e in errs)
```

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_n2_rejects_unknown_require -v`

Expected: FAIL.

- [ ] **Step 3: Implement N2**

```python
def _check_n2_requires(spec: InfoEdgeSpec) -> list[str]:
    from agent_lab.runtime.seams import KERNEL_SEAM_IDS
    provided: set[str] = set(KERNEL_SEAM_IDS)
    for n in spec.nodes:
        try:
            man = NodeRegistry.describe(n.factory)
        except KeyError:
            continue
        provided.update(man.provides)
    errs: list[str] = []
    for n in spec.nodes:
        try:
            man = NodeRegistry.describe(n.factory)
        except KeyError:
            continue
        for req in man.requires:
            if req not in provided:
                errs.append(
                    f"N2: node {n.id} requires {req!r} but no provider in spec or KERNEL_SEAM_IDS"
                )
    return errs
```

Same-spec `provides` counts (not full edge reachability). Kernel ids always count.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py tests/agent_lab/test_think_subgraph.py -q`

Expected: PASS. If a real worker `requires` a string not in `KERNEL_SEAM_IDS` and not provided, either add it to the frozenset (only for real Kernel seams) or delete the bogus `requires`.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/graph/validate.py agent_lab/runtime tests/agent_lab/test_validate_composition.py
git commit -m "feat(lab): N2 compile-time requires/provides closure"
```

---

### Task 9: `on_error=route` invokes then routes

**Files:**
- Modify: `agent_lab/runtime/runner.py` `_invoke_with_policy`
- Modify: `tests/agent_lab/test_error_routing.py`

**Interfaces:**
- Consumes: existing `_BoomAlways`, `_Sink`
- Produces: worker invoke count ≥ 1 on route; EXCEPTION content uses the raised error, not `node.skipped`

- [ ] **Step 1: Invert the skip test (this is the failing spec)**

Replace `test_on_error_route_skips_worker_invocation` with:

```python
def test_on_error_route_invokes_worker_then_delivers_exception() -> None:
    _reset_counters()
    spec = _spec(
        nodes=[
            _node("worker", "_boom_always", on_error=ErrorRoute.ROUTE, route_to="deny"),
            _node("deny", "_sink", ins=["exception"], outs=["handled"]),
        ],
    )
    compile_spec(spec, sub_registry={})
    trace = run_graph(spec, sub_registry={})
    assert _CALL_COUNTER.get("_boom_always", 0) == 1
    handled = trace.final_artifacts["handled"]
    assert handled.kind == ArtifactKind.EXCEPTION
```

Update `test_on_error_route_delivers_exception_to_target`: `error_class` must not be `node.skipped`. Use `make_exception(error_class=type(exc).__name__, message=str(exc), node_id=node.id, transient=False)` after the worker raises.

- [ ] **Step 2: Run inverted tests — they fail on current runner**

Run: `uv run pytest tests/agent_lab/test_error_routing.py::test_on_error_route_invokes_worker_then_delivers_exception tests/agent_lab/test_error_routing.py::test_on_error_route_delivers_exception_to_target -v`

Expected: FAIL (`_boom_always` count is 0).

- [ ] **Step 3: Fix runner**

Delete the pre-invoke `if node.on_error.value == "route":` short-circuit. Structure:

```python
try:
    outputs = invoke_node(node, inputs, self.seams)
    return outputs, "ok", error_info
except Exception as exc:
    if node.on_error.value == "route":
        return self._route_exception(node, exc)
    ... retry / fail ...
```

`_route_exception` writes EXCEPTION to `route_to`'s first IN, invokes the target, marks both executed.

Remove the defensive comment in `act.yaml` about not setting `on_error=route` (comment-only; no behavior change on act until Task 10).

- [ ] **Step 4: Run**

Run: `uv run pytest tests/agent_lab/test_error_routing.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/runtime/runner.py agent_lab/graphs/configs/act.yaml tests/agent_lab/test_error_routing.py
git commit -m "fix(lab): on_error=route invokes the worker before routing"
```

---

### Task 10: Split `act.execute` into route + body + receipts

**Files:**
- Create: `agent_lab/nodes/act/body/plugin.py`
- Create: `agent_lab/nodes/act/receipt_denied/plugin.py`
- Create: `agent_lab/nodes/act/receipt_none/plugin.py`
- Modify: `agent_lab/nodes/act/__init__.py`
- Modify: `agent_lab/graphs/configs/act.yaml`
- Modify: `agent_lab/nodes/act/execute/plugin.py` — delete or shrink to a re-export **deleted in this commit** (no shim)
- Move Body call from `execute/plugin.py` into `body/plugin.py`; keep `runtime_bind` / `configure_registry` on the Body worker until ADR-0209 lands, but **call them only via `seams["tool_registry"]` / `seams["safe_executor"]` if already injected; otherwise pass through existing `act_body` helpers and leave a single `configure_registry` on `body/plugin.py`**
- Test: `tests/agent_lab/test_act_subgraph.py`

**Interfaces:**
- Consumes: `act.authorize` OUT `authorized` with `verdict` in `{allow, deny, skip}`
- Produces: factories `act.body`, `act.receipt_denied`, `act.receipt_none`; `route_on` keyed by `authorized.content["verdict"]`

- [ ] **Step 1: Failing tests**

```python
def test_act_yaml_has_no_execute_factory() -> None:
    from agent_lab.graphs.loader import load_spec
    from pathlib import Path
    spec = load_spec(Path("agent_lab/graphs/configs/act.yaml"))
    factories = {n.factory for n in spec.nodes}
    assert "act.execute" not in factories
    assert "act.body" in factories
    assert "route_on" in factories


def test_act_deny_does_not_call_body(monkeypatch) -> None:
    # load act graph, feed authorized verdict=deny, assert receipt status=denied
    # and that act_body.run_body_act is not called (monkeypatch.setattr counter).
```

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/agent_lab/test_act_subgraph.py::test_act_yaml_has_no_execute_factory -v`

Expected: FAIL.

- [ ] **Step 3: Implement workers + YAML**

Use `act.dispatch` (one populated OUT) plus Task 10's required-IN skip so Body never runs on deny/skip. Do not use `route_on` for this split — `route_on` selects among already-computed inputs and would still invoke Body.

`receipt_denied`:

```python
@node(id="act.receipt_denied", layer=NodeLayer.EFFECT, kind=NodeKind.TRANSFORMER,
      inputs=[PortInfo("authorized", kind=PortKind.INTENT, required=False)],
      outputs=[PortInfo("receipt", kind=PortKind.RECEIPT)])
class ActReceiptDenied(Node):
    name = "act.receipt_denied"
    def execute(self, node, inputs, seams=None):
        c = getattr(inputs.get("authorized"), "content", {}) or {}
        return {"receipt": Artifact(kind=ArtifactKind.RECEIPT, content={
            "status": "denied", "tool": c.get("tool"), "decision_id": c.get("decision_id", ""),
            "action_type": str(c.get("action_type") or ""), "error": "grant denied",
        }, schema_ref="tool.receipt.v1")}
```

`receipt_none`: same with `status: "no_effect"`.

`act.body`: copy **only** the `verdict == "allow"` path from current `ActExecute.execute` (Body call + waiting_input + error receipt). Do not keep deny/skip branches.

`act.yaml` nodes after authorize:

```yaml
  - id: route
    factory: route_on
    config:
      key_from: authorized
      table:
        allow: allow_in
        deny: deny_in
        skip: skip_in
      default: skip_in
    ins: [authorized, allow_in, deny_in, skip_in]
    outs: [receipt]
```

Wiring: authorize.authorized fans to `body.authorized`, `receipt_denied.authorized`, `receipt_none.authorized`. `body.receipt` → `route.allow_in`, denied → `deny_in`, none → `skip_in`. `route.receipt` → `observe.receipt`.

If `route_on` cannot fan three live workers (it picks one **input** already computed), **do not run deny Body**. Prefer explicit edges + three workers all scheduled, with `route_on` selecting which receipt is observed — that would still invoke Body on deny.

Correct graph: **control split before Body**. Use three downstream nodes from authorize, only one enabled. Implement as:

Option used: `on_error` is the wrong tool. Add a tiny `act.dispatch` worker that reads verdict and returns **one** of three OUT ports populated, others absent, then edges `required: false` to body / denied / none.

```python
@node(id="act.dispatch", ...)
# outs: to_body, to_denied, to_none  — only one Artifact, others omitted
```

Runner already skips missing required edges if `required: False`. Set those three edges `required: false`. Body node `on_error=fail` only runs when `to_body` is present: **required IN missing → worker does not run** (spec §3). Mark `body.ins authorized` as required; missing → skip. Confirm runner: `"Missing port -> empty TEXT artifact"` today **does run** the node. That violates spec.

**In this task**, change `_run_node` input collection:

```python
missing = [p for p in node.ins if (node_id, p) not in self.store]
# optional ports: those listed in manifest as required=False
if missing_required:
    # skip invoke; do not raise
    self._executed.add(node_id)
    return
```

Add a test: node with required IN absent is not invoked.

Then deny path never calls Body.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/agent_lab/test_act_subgraph.py tests/plugins/lab/test_act_phase.py -q`

Expected: PASS. `rg "class ActExecute" agent_lab/nodes` = 0.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/nodes/act agent_lab/graphs/configs/act.yaml agent_lab/runtime/runner.py tests/agent_lab
git commit -m "feat(lab): split act.execute into dispatch, body, and receipts"
```

---

### Task 11: Grant + `borrow` (C4)

**Files:**
- Modify: `agent_lab/primitives/edge.py` (`grant_id: str | None = None`)
- Modify: `agent_lab/graphs/loader.py` (`_parse_edge` reads `grant`)
- Modify: `agent_lab/graph/validate.py` (borrow without grant / unknown grant / ports not in grant.ports → `"C4:"`)
- Modify: `agent_lab/runtime/runner.py` (propagate `borrow` like `data`, applying `max_bytes` / `redact`; violation → `_NonRetryableError`)
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: `InfoGrant`, `EdgeKind.BORROW`
- Produces: `Edge.grant_id`; C4 compile errors

- [ ] **Step 1: Failing tests**

```python
def test_c4_borrow_without_grant_fails() -> None:
    spec = InfoEdgeSpec(
        id="think",
        nodes=[InfoNode(id="expose", factory="think.expose", ins=["in_assembled_manifest"], outs=["messages"])],
        edges=[
            Edge(
                id="b",
                from_ref=PortRef(spec_id="perceive", node_id="commit", port_id="out_manifest"),
                to_ref=PortRef(spec_id="think", node_id="expose", port_id="in_assembled_manifest"),
                kind=EdgeKind.BORROW,
            )
        ],
    )
    errs = validate(spec)
    assert any(e.startswith("C4:") for e in errs)


def test_c4_borrow_with_grant_compiles() -> None:
    spec = InfoEdgeSpec(
        id="think",
        nodes=[InfoNode(id="expose", factory="think.expose", ins=["in_assembled_manifest"], outs=["messages"])],
        grants=[InfoGrant(id="g1", from_spec="perceive", to_spec="think", ports=["out_manifest"], mode="read")],
        edges=[
            Edge(
                id="b",
                from_ref=PortRef(spec_id="perceive", node_id="commit", port_id="out_manifest"),
                to_ref=PortRef(spec_id="think", node_id="expose", port_id="in_assembled_manifest"),
                kind=EdgeKind.BORROW,
                grant_id="g1",
            )
        ],
    )
    errs = validate(spec)
    assert not any(e.startswith("C4:") for e in errs)
```

Pydantic: add `grant_id` on `Edge` or the test will fail to construct. If Step 1 cannot even instantiate, add the field first with default `None` in the same task **after** the test is written (test file can use `model_construct` only if necessary — prefer adding the field then running the test).

- [ ] **Step 2: Run**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_c4_borrow_without_grant_fails tests/agent_lab/test_validate_composition.py::test_c4_borrow_with_grant_compiles -v`

Expected: FAIL on missing C4.

- [ ] **Step 3: Implement field + validate + runner copy**

```python
# Edge
grant_id: str | None = None
```

Loader: `grant_id=raw.get("grant")`.

Validate: every `kind=borrow` has `grant_id` referencing `spec.grants`; `from_ref.spec_id == grant.from_spec`; `to_ref.spec_id == grant.to_spec`; `from_ref.port_id in grant.ports`.

Runner edge loop: treat `borrow` like `data`/`project` for copy. If `grant.max_bytes` and `len(json.dumps(art.content)) > max_bytes`: raise `_NonRetryableError`. If `grant.redact`: shallow-drop those dict keys before copy (new Artifact).

Parent `input_map` remains the downward injection path and does **not** need a Grant.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py tests/agent_lab/test_act_subgraph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/primitives/edge.py agent_lab/graph agent_lab/graphs/loader.py \
  agent_lab/runtime/runner.py tests/agent_lab/test_validate_composition.py
git commit -m "feat(lab): C4 borrow edges require InfoGrant"
```

---

### Task 12: C1 project-closure canary

**Files:**
- Modify: `agent_lab/graph/validate.py` (optional `sub_registry` already unused; pass it from `compile` → `validate(spec, sub_registry)`)
- Modify: `agent_lab/graph/compile.py` (`validate(spec, sub_registry)`)
- Test: `tests/agent_lab/test_validate_composition.py`

**Interfaces:**
- Consumes: `sub_registry` of nested specs; `EdgeKind.PROJECT` / `DATA`
- Produces: `"C1:"` if an `effect` receipt OUT cannot reach a `project` edge into a `region=model_visible` node

Scope for this task: **act → model_eye** only. Walk: `act.execute`/`act.body`/`act.observe` receipt/observation along `data` to a `project` edge whose `to_ref.spec_id` has `region` model_visible **or** id `model_eye`. Missing `e_observe_to_model_eye` fails.

- [ ] **Step 1: Failing test**

```python
def test_c1_act_without_project_to_model_eye_fails() -> None:
    from agent_lab.graphs.loader import load_spec
    from pathlib import Path
    from copy import deepcopy
    spec = load_spec(Path("agent_lab/graphs/configs/act.yaml"))
    spec = spec.model_copy(update={"edges": [e for e in spec.edges if e.id != "e_observe_to_model_eye"]})
    errs = validate(spec)
    assert any(e.startswith("C1:") for e in errs)
```

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_c1_act_without_project_to_model_eye_fails -v`

Expected: FAIL.

- [ ] **Step 3: Implement the canary**

If spec id is `act` (or any spec with an `effect` edge / `act.observe` node), require at least one `kind=project` edge from this spec to another spec. Do not attempt full graph reachability across the whole loop in this task.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py tests/agent_lab/test_act_subgraph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_lab/graph/validate.py agent_lab/graph/compile.py tests/agent_lab/test_validate_composition.py
git commit -m "feat(lab): C1 canary — act observation must project to model_eye"
```

---

### Task 13: N7 worker-import lint + N8 no `relates_to`

**Files:**
- Create: `scripts/check_agent_lab_node_imports.py`
- Modify: `agent_lab/nodes/manifest.py` (remove `relates_to` from `NodeManifest` and `@node`)
- Modify: every `@node(..., relates_to=...)` call site — drop the kwarg
- Test: `tests/agent_lab/test_validate_composition.py` (invokes the script on a temp tree) **and** run the script on `agent_lab/nodes`

**Interfaces:**
- Consumes: AST of `agent_lab/nodes/**/plugin.py`
- Produces: exit 1 if `from agent_lab.nodes.<other_worker>` imports appear, except `base` / `manifest` / `host`

- [ ] **Step 1: Failing tests**

```python
def test_n7_script_flags_sibling_import(tmp_path: Path) -> None:
    # write a fake plugin.py that imports agent_lab.nodes.act.execute.plugin
    # run check_agent_lab_node_imports.main([str(tmp_path)]) expect nonzero
```

```python
def test_n8_node_decorator_rejects_relates_to() -> None:
    import inspect
    from agent_lab.nodes.manifest import node
    assert "relates_to" not in inspect.signature(node).parameters
```

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_n8_node_decorator_rejects_relates_to -v`

Expected: FAIL (`relates_to` still in signature).

- [ ] **Step 3: Implement**

Script walks `agent_lab/nodes`, skips `base.py`/`manifest.py`, forbids `ImportFrom` where module startswith `agent_lab.nodes.` and the remainder is not `{base, manifest, host}`. Allow `from agent_lab.nodes.act.execute import body` **until Task 10 deleted it**; after Task 10 this must be 0.

Strip `relates_to` from decorator and dataclass. `rg relates_to agent_lab/nodes` = 0.

- [ ] **Step 4: Run**

```bash
uv run python scripts/check_agent_lab_node_imports.py
uv run pytest tests/agent_lab/test_validate_composition.py::test_n7_script_flags_sibling_import \
  tests/agent_lab/test_validate_composition.py::test_n8_node_decorator_rejects_relates_to -q
rg relates_to agent_lab/nodes
```

Expected: script exit 0; tests PASS; rg empty.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_agent_lab_node_imports.py agent_lab/nodes tests/agent_lab/test_validate_composition.py
git commit -m "feat(lab): N7 forbid worker-to-worker imports; drop relates_to"
```

---

### Task 14: Atomic subgraph `output_map` + delete-when gate

**Files:**
- Modify: `agent_lab/runtime/runner.py` `_run_subgraph`
- Test: `tests/agent_lab/test_validate_composition.py`
- Modify: [docs/notes/proposed/primitive/2026-09-09-agent-lab-graph-node-composition.md](../proposed/primitive/2026-09-09-agent-lab-graph-node-composition.md) → move to `docs/notes/implemented/primitive/` only if every acceptance line below is true; rewrite `## Proposal` to `## Decision` present tense in **this** commit

**Interfaces:**
- Consumes: child `run()` either returns a full export dict or raises
- Produces: parent store updated iff every `output_map` key is in child outputs; on exception, no parent OUT from that link

- [ ] **Step 1: Failing test**

```python
def test_subgraph_failure_does_not_leak_partial_exports() -> None:
    # Parent host graph.call with sub_spec that has two outs; child worker
    # writes first OUT then raises. Parent finals must not contain the first OUT.
```

Build a tiny child spec: node A writes `a`, node B (`_boom_always`) after A. Parent `output_map: {a: a_out, b: b_out}`. After `run_graph` raises, if the test catches the error, assert parent store was not updated — easiest: wrap `run()` and inspect that the raised error leaves `trace.final_artifacts` without `a_out`.

If `run()` currently fills partial then raises, the test fails until `_run_subgraph` buffers:

```python
child_outputs = child.run()
missing = [sub for sub in link.output_map if sub not in child_outputs]
if missing:
    raise RuntimeError(f"sub_spec {link.sub_spec_id} missing exports {missing}")
for sub_port, parent_port in link.output_map.items():
    self.store[(link.node_id, parent_port)] = child_outputs[sub_port]
```

On exception from `child.run()`, do not write any mapping (let it propagate).

- [ ] **Step 2: Run to fail**

Run: `uv run pytest tests/agent_lab/test_validate_composition.py::test_subgraph_failure_does_not_leak_partial_exports -v`

Expected: FAIL if partial leak exists; if already atomic, test PASS and skip Step 3 code.

- [ ] **Step 3: Buffer output_map writes**

As above.

- [ ] **Step 4: Delete-when commands (must all hold before promoting the Note)**

```bash
rg ControlSlotsPlugin agent_lab/          # empty
rg PHASE_OWNER_WIRING agent_lab/          # empty
rg semantic_router agent_lab/             # empty
rg "class ActExecute" agent_lab/nodes     # empty
python -m agent_lab.run --describe --target graph:agent_loop
uv run pytest tests/agent_lab tests/plugins/lab -q
uv run ruff check agent_lab tests/agent_lab tests/plugins/lab
uv run python scripts/check_agent_lab_node_imports.py
```

Describe must show `stop_decide` and the `remember.state_ref` edge. If any command fails, **do not** move the Note.

- [ ] **Step 5: Promote Note + commit**

Move `docs/notes/proposed/primitive/2026-09-09-agent-lab-graph-node-composition.md` → `docs/notes/implemented/primitive/`. `Status: implemented`. Rewrite `## Proposal` to present-tense `## Decision`. Fold Acceptance/Risks into `## Consequences` / `## Verification`. Keep Alternatives.

```bash
git add agent_lab/runtime/runner.py tests/agent_lab/test_validate_composition.py docs/notes
git commit -m "feat(lab): atomic subgraph exports; implement graph-node composition note"
```

---

## Self-review (spec coverage)

| Spec rule | Task |
|---|---|
| Three planes / Kernel not a graph | Global Constraints (no task graphifies Kernel) |
| Worker ports + no `config.from/to` as port SSOT | 2 |
| `execute(..., seams)` | 7 |
| Host = `graph.call`, one `sub_spec` | 1, 4 |
| Sibling control hosts, delete insertion plugin | 4 |
| Five edge kinds; N5 | 3, 11 |
| Grant + borrow | 11 |
| `before_compile` cannot rewrite topology | 5 |
| Observation read-only; delete semantic_router | 6 |
| N2 requires | 8 |
| Route after invoke | 9 |
| Split `act.execute` | 10 |
| N7 / N8 | 13 |
| Atomic `output_map` | 14 |
| C1 canary | 12 |
| Promote Note / delete-when | 14 |

No placeholders remain. Types: `SeamMap`, `KERNEL_SEAM_IDS`, `graph.call`, `grant_id`, `load_closure`, `act.body`, `act.dispatch`/`route` as specified per task.
