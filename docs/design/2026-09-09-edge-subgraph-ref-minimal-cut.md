# Edge-level subgraph reference — minimal cut-in

> Status: proposed. Companion to brainstorming chat — awaits approval before
> implementation. delete-when: superseded by ADR-0206/0207 once the graph
> kernel becomes the SSOT for nested-graph traversal.

## 1. Problem

`declarative-phase-graph.yaml` today is one flat graph; an edge can only
say `source → target`. Operators who want to express "from `reflect.main`,
spawn a small sub-flow that reuses a few phase executors and returns a
result for the original edge" have no config knob — they must hand-wire a
second plan and invoke it from a custom executor.

The user wants the **smallest possible config-level cut-in** that
demonstrates the shape of a graph-to-graph reference (the "图B 终极形态"
they had in mind), without changing the cognitive closed set, the contract
surface, or the runtime dispatch model.

## 2. Where we cut

`PhaseEdge` (in `lca/contracts/protocols/declarative/declarative_1/declarative_graph.py:84`)
is a frozen dataclass with `source / target / when / loop`. Edges are
already consumed by `GenericPlanInterpreter._select_edge`
(`lca/harness/graph/execute/interpreter.py:501`), where one branch can
handle "this edge actually refers to another plan" without touching the
six-phase executor dispatch.

The cut-in is therefore **one optional dataclass field plus one interpreter
branch** — no new runtime, no new event vocabulary, no new phase.

### 2.1 Why an edge, not a node

| Candidate | Surface area | Risk |
|---|---|---|
| `PhaseEdge.subgraph_ref` | 1 dataclass field + 1 branch in `_select_edge` | Low — edge is pure config consumed only by interpreter |
| `PhaseNode.graph_ref` | New field on `PhaseNode`, new contract on every PhaseExecutor, touches assembler (`PG-001`) | High — entangles executor contract (C13 risk) |
| New `SubgraphTransition` event | Touches `EXECUTION_POINTS` whitelist (C11) | High — closed-set change requires ADR |

Edge wins.

## 3. The new field

```python
# lca/contracts/protocols/declarative/declarative_1/declarative_graph.py
@dataclass(frozen=True, slots=True)
class PhaseEdge:
    source: str
    target: str
    when: str
    loop: LoopGuard | None = None
    subgraph_ref: SubgraphReference | None = None   # NEW — frozen dataclass default
```

`SubgraphReference` is its own frozen dataclass so we don't string-parse
later:

```python
@dataclass(frozen=True, slots=True)
class SubgraphReference:
    plan_ref: str            # bundle-relative path or absolute plan identity
    entry_node: str          # the node the subgraph starts at
    binding_edge: str        # the edge in the outer graph (proves mutual ref)
    return_on: str = "next"  # for now, only "next" is supported
```

`binding_edge == self.source` is the **mutual reference check** the user
described: 图A's edge names the graph, the graph's reference names 图A's
edge. Both sides know each other by id.

## 4. Bundle shape

A new minimal bundle:

```yaml
# bundles/reflect-subgraph.yaml
name: reflect-subgraph
entries:
  - id: phase.topology.reflect_subgraph
    $module: lca.plugins.loop.graph.topology.standard.plugin
    config:
      nodes:
        - id: reflect.inner_score
          phase: reflect
          binding: phase.reflect.standard
          max_visits: 4
          entry: true
        - id: reflect.inner_summarize
          phase: reflect
          binding: phase.reflect.standard
          max_visits: 4
  - id: phase.edge.reflect_subgraph
    $module: lca.plugins.loop.graph.edges.standard.plugin
    config:
      edges:
        - source: reflect.inner_score
          target: reflect.inner_summarize
          when: true
        - source: reflect.inner_summarize
          target: reflect.inner_score   # bounded loop inside the subgraph
          when: not result.payload.keep_going
          loop:
            max_iterations: 3
            terminal_predicate: result.payload.keep_going == false
```

And the cut-in in `declarative-phase-graph.yaml`:

```yaml
- id: phase.edge.standard
  $module: lca.plugins.loop.graph.edges.standard.plugin
  config:
    edges:
      ...
      - source: reflect.main
        target: remember.main        # kept — fallback target if subgraph refuses
        when: result.result_kind == "phase_error"
      - source: reflect.main
        target: remember.main        # happy path — points at subgraph
        when: true
        subgraph_ref:
          plan_ref: bundles/reflect-subgraph.yaml
          entry_node: reflect.inner_score
          binding_edge: reflect.main
          return_on: next
```

## 5. Interpreter branch

In `lca/harness/graph/execute/interpreter.py:_drive`, after
`_select_edge` returns an edge:

```python
edge = self._select_edge(graph.edges, node.id, result, traversal.artifacts, state)
if edge is None:
    break
if edge.subgraph_ref is not None:
    sub_state = await self._run_subgraph(
        edge.subgraph_ref,
        executable=executable,
        state=state,
        input=phase_input,
        artifacts=traversal.artifacts,
    )
    # Mutate state from the subgraph's deltas, then continue the OUTER graph
    state = sub_state
    next_source = edge.target
    # Resume outer loop with the subgraph's terminal PhaseResult
else:
    next_source = edge.target
```

`_run_subgraph` is a private helper that:

1. Resolves `subgraph_ref.plan_ref` via the existing `PlanResolutionService`
   (already in `lca/application/runtime/plan_resolution.py:54`) — no new
   resolver.
2. Builds the subgraph `ExecutablePlan` via `GraphAssembler().assemble(...)`.
3. Re-enters `_drive` recursively with the subgraph's `phase_graph` and
   `entry_node`.
4. Returns the merged `state` (subgraph's deltas have been folded through
   the same `Reducer`; C4 holds).
5. Stamps a `subgraph.returned` lifecycle event via the existing
   `lifecycle_publisher` — reuses the existing closed set, no new EP
   (C11 holds).

**Depth limit:** recursion is capped at `subgraph_ref.return_on == "next"`
and a hard max-depth constant (`MAX_SUBGRAPH_DEPTH = 4`). No subgraph of
subgraphs in this experiment (the user did not ask for it; YAGNI).

## 6. Mutual-reference check (compile-time)

In `lca/harness/declarative/compile/assembler/assembler.py:GraphAssembler.assemble`,
add one validation:

```python
for edge in plan.phase_graph.edges:
    if edge.subgraph_ref is None:
        continue
    sub_plan = self._resolve_subgraph_plan(edge.subgraph_ref.plan_ref)
    if edge.subgraph_ref.entry_node not in {n.id for n in sub_plan.phase_graph.nodes}:
        raise DeclarativeValidationError(
            "PG-004",
            f"edge {edge.source!r} subgraph_ref.entry_node "
            f"{edge.subgraph_ref.entry_node!r} not present in referenced plan",
        )
    # Mutual-reference check (the user's "this graph also configures
    # this specific point" requirement):
    for back_edge in sub_plan.phase_graph.edges:
        if (
            back_edge.subgraph_ref is not None
            and back_edge.subgraph_ref.plan_ref == edge.source
        ):
            break
    else:
        raise DeclarativeValidationError(
            "PG-004",
            f"edge {edge.source!r} subgraph_ref requires the referenced plan to "
            f"declare a back-reference naming {edge.source!r}",
        )
```

This is the **two-graph mutual reference** the user described, expressed
as a compile-time invariant — if 图A's edge points at 图B, then 图B must
declare an edge whose `subgraph_ref.plan_ref` names 图A's edge id. Both
sides of the reference are validated at compile; the runtime never sees
an asymmetric ref.

## 7. Error handling

| Failure | Detection | Behavior |
|---|---|---|
| `plan_ref` path does not resolve | `PlanResolutionService` raises `PlanResolutionError` | Assembler bubbles as `PG-004` (compile-time) |
| `entry_node` not in referenced plan | Assembler iteration | `PG-004` at compile |
| Missing mutual-reference edge | Assembler iteration | `PG-004` at compile |
| Subgraph hits `MAX_SUBGRAPH_DEPTH` | `_run_subgraph` recursive guard | `DeclarativeValidationError("PG-005", ...)` at runtime — fail-loud |
| Subgraph node fails phase execution | Existing `PhaseExecutionTransaction` error path | Bubbles as today; outer edge `when` predicate still applies on return |
| `Reducer` delta fails | Existing `RegistryDeltaReducer` raises `PG-003` | Bubbles as today |
| Loop guard exhausted inside subgraph | Existing `DeclarativeLoopGuardEvaluator` | Subgraph terminates, returns to outer with terminal result |

No new error categories; everything folds into existing `PG-001` / `PG-003` /
`PG-004` / `PG-005` codes (last one is the new depth-limit code).

## 8. Verification

| Layer | Command | Expected |
|---|---|---|
| Static | `ruff check` | clean |
| Static | `ruff format --check` | clean |
| Static | `./scripts/lca-ops lint-imports` | no new violation |
| Contract | `pytest tests/contracts/test_phase_edge_subgraph.py -v` | new tests pass |
| Compile | `pytest tests/harness/declarative/compile/test_subgraph_ref_validation.py -v` | PG-004 cases pass |
| Runtime | `pytest tests/harness/graph/execute/test_interpreter_subgraph.py -v` | recursion + depth limit + state merge cases pass |
| Plugin shape | `./scripts/lca-ops audit-plugin-shape` | `phase.edge.standard` and `phase.topology.standard` unchanged shape (we only added a dict key) |
| End-to-end | `pytest tests/declarative/test_phase_graph.py -v` | existing tests unchanged |

Test coverage required:

- **Happy path:** outer edge with `subgraph_ref` runs the subgraph and returns; outer state reflects subgraph deltas.
- **Compile rejection A:** `plan_ref` path doesn't resolve → `PG-004`.
- **Compile rejection B:** `entry_node` missing from referenced plan → `PG-004`.
- **Compile rejection C:** mutual-reference edge missing → `PG-004`.
- **Depth limit:** chain of 5 → `PG-005` at 5th.
- **Reducer isolation:** subgraph delta does NOT leak into outer journal stream until the outer resume point.

## 10. What this does NOT do (YAGNI)

- No subgraph of subgraphs (depth 1 only).
- No node-level `graph_ref` (edge only).
- No new event in `EXECUTION_POINTS` (lifecycle event reuse only).
- No new `PhaseExecutor` contract.
- No new ADR. (Cognitive closed set is untouched; this is config-layer
  feature inside existing SSOT. If the user later wants depth > 1 or
  node-level refs, that becomes an ADR.)
- No COMPAT shim. Either it lands clean or it doesn't land.

## 11. Rollback

Single-PR rollback: revert the dataclass field, the interpreter branch,
the assembler validation, and remove `bundles/reflect-subgraph.yaml`. No
follow-up debt because nothing else depends on `subgraph_ref` in this
experiment.