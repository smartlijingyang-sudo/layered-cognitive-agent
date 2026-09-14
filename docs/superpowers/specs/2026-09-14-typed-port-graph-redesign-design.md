# Typed Port Graph Redesign

| | |
|---|---|
| **Status** | Draft (brainstorming approved, awaiting writing-plans) |
| **Date** | 2026-09-14 |
| **Owners** | Graph kernel team |
| **Scope** | Atomic cutover of the v2 graph kernel, contracts, predicates, bundles, and plugins to a typed-port graph |
| **Closes** | Root cause of repeated "graph looks healthy but outcome=failure" bugs; specifically the silent-`None` failure mode in `_ResultView.__getattr__` |

## 0. Motivation

The v2 graph kernel (`lca/framework/graph/`) drives declarative phase graphs through typed nodes. Cross-node data flow today goes through two parallel, fragile mechanisms:

1. **`NodeOutput.port_values: Mapping[PortName, Any]`** — typed port store, the actual contract.
2. **`_ResultView.__getattr__(name)`** — duck-typed view over `NodeOutput` that returns `None` for any unknown attribute, used by edge predicates to read `result.payload.decision.action_type`-style nested paths.

The two mechanisms are **out of sync**: profiles write `when: result.payload.decision.action_type == "use_tool"` (PhaseResult-era shape), but the v2 kernel never produces a `.payload` field. The duck-type fallback silently returns `None`, predicates evaluate to `False`, edges never fire, and `reducer` sees a think phase that "ran but had no downstream routing" — it calls `apply_error → apply_stop`, and the run terminates with `outcome=failure` while the graph itself looks 100% healthy.

This bug class is **not a one-off**. Every new predicate expression is at risk of the same silent failure. Three real reproductions in the same session:

- `bundles/phase_main_outer.yaml` — `result.payload.decision.action_type == "use_tool"` (silent None)
- `bundles/phase_main_outer.yaml` — `result.payload.decision.action_type == "respond" and result.payload.decision.response_text != ""` (silent None)
- `bundles/declarative-phase-graph.yaml` — five predicates reading `result.payload.should_stop` (silent None)

The fix is not "patch the duck-type to not return None" — the fix is to **delete the duck-type entirely** and make every cross-node read a typed, lift-validated, fail-loud reference.

## 1. Design overview

### 1.1 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Plan SDK (agent-author surface, Pydantic-typed)            │
│  Plan / NodeSpec / EdgeSpec / Predicate                     │
└──────────────────────────────────────────────────────────────┘
              │  serialize (YAML, deterministic)
              ▼
┌──────────────────────────────────────────────────────────────┐
│  Plan / NodeSpec / EdgeSpec / Predicate (frozen, validate) │
└──────────────────────────────────────────────────────────────┘
              │  lift
              ▼
┌──────────────────────────────────────────────────────────────┐
│  Plan Kernel │
│  - PortRegistry (typed port store)                            │
│  - PortReader (typed resolver for predicates)                │
│  - PredicateEvaluator (typed predicate solver)               │
│  - PlanInterpreter (loop)                                    │
│  - StrategyRegistry (binding kinds)                          │
└──────────────────────────────────────────────────────────────┘
              │  uses
              ▼
┌──────────────────────────────────────────────────────────────┐
│  NodeStrategy / SubgraphStrategy                             │
│  - declares IO schema (input/output port names)             │
│  - returns NodeOutput (port_values + routing)                │
│  - knows NOTHING about other nodes, edges, predicates │
```

### 1.2 Invariants

1. **Port names are the contract.** A node's IO schema declares which port names it reads and writes. The kernel enforces at lift time that every read resolves to a real declared output port of a real predecessor node.
2. **Predicates are typed expressions over port names.** No string `when: result.payload.decision.action_type == "use_tool"` — the predicate is a structured object that references port names by symbol.
3. **Compile-time exhaustiveness.** Lifting a plan validates: (a) every node's required input port is produced by some predecessor, (b) every port name in every predicate is a declared output of the source node, (c) every `Predicate.field` exists on the port's `payload_type`, (d) every plan has a termination policy.
4. **Nodes are blind to topology.** A node strategy receives `NodeInput(port_values=...)` and returns `NodeOutput(port_values=..., routing=RoutingDecision(...))`. It does not see edges, other nodes, or predicates.
5. **Atomic cutover.** No `_ResultView`, no `__getattr__` fallback, no silent None. An unknown port name in a predicate is a `PlanLiftError` at construction with structured context, not a silent False at runtime.

## 2. Contract

### 2.1 `Predicate` and `PortRef`

```python
class PortRef(BaseModel):
    """Symbolic reference to a port on the source node of an edge.
    Resolved by the kernel against the source node's declared outputs.
    Fails at lift time if the source node does not declare this port.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: PortName                       # e.g. "decision"
    field: str | None = None             # e.g. "action_type" — typed against port.payload_type


class Predicate(BaseModel):
    """Typed, structured predicate over port names.

    Replaces string DSL (`when: result.payload.decision.action_type == "use_tool"`).
    Recursive: leaf kinds compare a port value to a constant; inner kinds
    combine via and/or/not. No attribute paths, no string parsing, no AST.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["eq", "ne", "in", "exists", "missing", "and", "or", "not"]
    port: PortRef | None = None          # for leaf kinds
    value: Any | None = None             # for leaf kinds, typed against port.payload_type
    children: tuple["Predicate", ...] = ()  # for boolean kinds
```

### 2.2 `RoutingDecision`

```python
class RoutingDecision(BaseModel):
    """Typed control-plane output every decision-producing node emits.
    The kernel reads the same port store — no separate control channel.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    action_type: ActionType              # enum, not string
    should_terminate: bool = False
    next_hint: str | None = None         # free-form metadata, not routing
```

Replaces the three ad-hoc fields `NodeOutput.result_kind`, `NodeOutput.next_hint`, `NodeOutput.next_hints`.

### 2.3 Extended `PortSpec` and `NodeIOSchema`

```python
class PortSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: PortName
    required: bool = True
    payload_type: type[BaseModel] | None = None  # was optional; now load-bearing


class NodeIOSchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    inputs: tuple[PortSpec, ...]
    outputs: tuple[PortSpec, ...]
    # Plan-level termination, evaluated after every visit.
    # The kernel picks the FIRST node whose terminal_predicate matches.
    terminal_predicate: Predicate | None = None
```

`payload_type` is now load-bearing for lift-time validation of `Predicate.field` references. When `None`, predicates may still reference the port by name but cannot use `field` (lift rejects `field is not None` on a port with `payload_type is None`).

### 2.4 `PlanEdge.when`

```python
class PlanEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: NodeId
    target: NodeId
    when: Predicate                        # was: str
```

### 2.5 Errors

```python
class PlanLiftError(ValueError):
    """Raised at plan construction when:
    - a Predicate references a port the source node doesn't declare
    - a Predicate.field doesn't exist on the port's payload_type
    - a node's required input port is never produced by any predecessor
    - an edge's `from` node isn't in the plan
    - the plan has no termination policy
    """
    plan_id: str | None = None
    node_id: str | None = None
    edge_id: str | None = None
    port_name: str | None = None
    reason: str


class UnsetPortError(PlanLiftError): ...   # runtime: port never written
class UnknownFieldError(PlanLiftError): ...  # runtime: payload_type missing field (should be impossible post-lift)
```

## 3. Kernel semantics

### 3.1 `PlanInterpreter.run` new loop

```
while not traversal.terminated():
    node = plan.node(traversal.current_id)

    input = port_registry.build_input(node.io_schema, consumer_node=node.id)
    strategy = registry.resolve(node.binding)
    output = await strategy.execute(ctx, input)

    node.io_schema.project_outputs(output.port_values)   # raises NodeSchemaError on unknown keys
    port_registry.merge_output(output.port_values)

    if node.io_schema.terminal_predicate is not None:
        reader = PortReader(source_node=node.id, registry=port_registry)
        if evaluate_predicate(node.io_schema.terminal_predicate, reader=reader):
            traversal.terminate(reason="terminal_predicate")
            observer.observe(visit_end_terminal)
            break

    edge = select_edge(plan.edges, current_id, port_registry)
    if edge is None:
        traversal.terminate(reason="no_edge_match")
    else:
        traversal.advance(edge=edge)
```

### 3.2 `PortReader`

```python
class PortReader(BaseModel):
    """Typed read-only view over PortRegistry for edge predicate evaluation.

    Constructed per-edge by the kernel. Resolves PortRef against the
    edge source node's declared output ports. Lift-time validation
    guarantees that every read is against a declared port; runtime
    can only fail on UnsetPortError (port never written).
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_node: str
    registry: PortRegistry

    def read(self, ref: PortRef) -> Any:
        port_value = self.registry.read(ref.name)
        if port_value is None:
            raise UnsetPortError(...)
        if ref.field is None:
            return port_value
        payload_type = self.registry.port_type(ref.name)
        if ref.field not in payload_type.model_fields:
            raise UnknownFieldError(...)
        return getattr(port_value, ref.field)
```

`_ResultView` is deleted. No `__getattr__` fallback.

### 3.3 `PredicateEvaluator`

```python
def evaluate_predicate(pred: Predicate, *, reader: PortReader) -> bool:
    if pred.kind == "and":
        return all(evaluate_predicate(c, reader=reader) for c in pred.children)
    if pred.kind == "or":
        return any(evaluate_predicate(c, reader=reader) for c in pred.children)
    if pred.kind == "not":
        return not evaluate_predicate(pred.children[0], reader=reader)
    actual = reader.read(pred.port)
    if pred.kind == "exists":
        return actual is not None
    if pred.kind == "missing":
        return actual is None
    if pred.kind == "eq":
        return actual == pred.value
    if pred.kind == "ne":
        return actual != pred.value
    if pred.kind == "in":
        return actual in pred.value
```

No `ast.parse`. No string parsing. No silent None.

### 3.4 Plan termination

`terminal.commit` outer node is removed. Termination is expressed two ways:

1. **`NodeIOSchema.terminal_predicate`** — predicate evaluated after each visit.
2. **`max_visits` exhausted** — existing behavior, unchanged.

The reducer's `apply_terminal_outcome` still runs after the kernel exits; that's reducer-layer, not graph-layer.

### 3.5 Subgraph nodes

`SubgraphStrategy` and the `close_out_adapter` keep their role (subgraph → outer port translation), but the adapter shrinks dramatically because the typed `payload_type` makes most renames generic.

## 4. Migration scope

Atomic cutover, no COMPAT shim (user-confirmed scope).

### 4.1 Layer 1 — Contracts (`lca/contracts/protocols/graph/`)

| File | Change |
|---|---|
| `node_io.py` | `PortSpec.payload_type` is no longer informational — it is now load-bearing for predicate `field` validation. `NodeIOSchema` gains `terminal_predicate`. `NodeOutput` loses `result_kind`, `next_hint`, `next_hints`. |
| `plan.py` | `PlanEdge.when: str` → `Predicate`. |
| `predicate.py` (NEW) | `Predicate`, `PortRef`, helpers. |
| `routing.py` (NEW) | `RoutingDecision`. |
| `errors.py` (NEW) | `PlanLiftError`, `UnsetPortError`, `UnknownFieldError`. |

### 4.2 Layer 2 — Kernel (`lca/framework/graph/`)

| File | Change |
|---|---|
| `interpreter.py` | Delete `_ResultView`. Add `PortReader` construction. terminal_predicate evaluation. |
| `traversal.py` | `select_edge` takes `PortReader`, not `result: object`. Delete `_default_predicate` fallback. |
| `port_registry.py` | Add `read(name)` + `port_type(name)`. Existing `merge_output` / `set_outer_input` unchanged. |
| `lifter.py` | `lift_graph_spec` runs predicate validation; raises `PlanLiftError` with structured context. |
| `predicate_evaluator.py` (NEW) | `evaluate_predicate(pred, reader)`. |

### 4.3 Layer 3 — Strategies (`lca/plugins/{think,act,...}/`)

Mostly additive. Plugins keep their IO schema; migration updates output port maps:

- `think/classify.py`: emits `decision` + `routing` (replaces `response`+`delegations`+`intent`+`tool_calls`)
- `act_subgraph/`: reads `decision`, emits `act_outcome` + `routing` (replaces `decision`+`should_terminate`)
- `reflect/`, `remember/`: emit `reflection_verdict`, `memory_record`

Each plugin's `enter()` and `execute()` shape unchanged.

### 4.4 Layer 4 — Bundles (`bundles/*.yaml`)

Mechanical rewrite of every `when:` clause. ~12 bundles affected. Examples below in §5.

### 4.5 Layer 5 — Tests

| File | Purpose |
|---|---|
| `tests/framework/graph/test_predicate_evaluator.py` (NEW) | Pure-function tests for `evaluate_predicate`. |
| `tests/framework/graph/test_plan_lift.py` (NEW) | Lift-time validation tests — every broken YAML from current code becomes a `PlanLiftError` test case. |
| `tests/framework/graph/test_port_reader.py` (NEW) | PortReader read semantics. |
| `tests/integration/test_end_to_end_think_to_act.py` (NEW) | The bug we just found becomes a regression test: a think → act round-trip MUST complete when `routing.action_type == "use_tool"`. |
| `tests/lca_kernel/plan/test_phase_main_outer_lift.py` (NEW) | Atomic lift test — if `phase_main_outer.yaml` can't lift, CI fails. |

### 4.6 Layer 6 — Close-out adapter

`cognition/wire/close_out_adapter.py` shrinks by ~70%. Logic becomes generic: "for each outer output port, copy from inner port by name (or rename map if present)." Adapter-specific magic stays only for genuine cross-DTO renames (e.g. `act_outcome` ↔ `observation`).

### 4.7 Deletions in the same PR

- `_ResultView` in `interpreter.py`
- `_default_predicate` fallback in `traversal.py`
- `result_kind` / `next_hint` / `next_hints` fields on `NodeOutput`
- String-typed `when:` fields on `PlanEdge`
- `terminal.commit` outer node

### 4.8 Migration sequence within the PR (each step compiles + tests)

1. Add new types (`Predicate`, `RoutingDecision`, `PlanLiftError`) — no consumers yet
2. Extend `PortSpec.payload_type` (load-bearing when present; field-restricted when None) + `NodeIOSchema.terminal_predicate`
3. Add `predicate_evaluator.py` + `port_reader`
4. Replace `_ResultView` with `PortReader` in `interpreter.py`
5. Change `PlanEdge.when` to `Predicate`; update lifter to validate
6. Rewrite each bundle YAML
7. Rewrite each strategy's output port map
8. Shrink `close_out_adapter`
9. Delete deprecated fields/nodes/fallback
10. Full integration test pass

## 5. Example: rewrite `bundles/phase_main_outer.yaml`

Before (broken):
```yaml
edges:
  - from: think.main
    to: act.main
    when: result.payload.decision.action_type == "use_tool"
  - from: think.main
    to: terminal.commit
    when: result.payload.decision.action_type == "respond" and result.payload.decision.response_text != ""
  - from: act.main
    to: think.main
    when: result.payload.decision.action_type == "use_tool"
  - from: act.main
    to: terminal.commit
    when: result.payload.should_terminate == true
```

After:
```yaml
edges:
  - from: think.main
    to: act.main
    when:
      kind: eq
      port: { name: routing, field: action_type }
      value: use_tool
  - from: think.main
    to: terminal.commit
    when:
      kind: and
      children:
        - { kind: eq, port: { name: routing, field: action_type }, value: respond }
        - { kind: ne, port: { name: decision, field: response_text }, value: "" }
  - from: act.main
    to: think.main
    when:
      kind: eq
      port: { name: routing, field: action_type }
      value: use_tool
  - from: act.main
    to: terminal.commit
    when: { kind: eq, port: { name: routing, field: should_terminate }, value: true }
```

Verbose but self-describing at a glance — correct tradeoff for a "human reads, agent writes" surface.

## 6. Industry alignment

| Framework | Concept | New design maps to |
|---|---|---|
| Dagster | `Op` + typed `In`/`Out` | `NodeIOSchema(inputs, outputs)` |
| Dagster | `AssetKey` + `AssetSensor` | `Predicate(PortRef)` + `terminal_predicate` |
| LangGraph | `StateGraph` + `state_schema` | `Plan` + `NodeIOSchema` (multi-port, not single-state) |
| LangGraph | `Command(goto=...)` | `RoutingDecision` |
| Airflow | XCom store | `PortRegistry` |
| Prefect | TaskFlow API (`@task`) | `NodeStrategy.execute` |
| Apache Beam | `PCollection` + `ParDo` | `port store` + `NodeStrategy` |

The redesign **does not invent a new paradigm**. It applies Dagster / LangGraph patterns to a kernel that currently uses Python AST duck-typing — standing on shoulders.

## 7. Future considerations (contract-ready, not implemented now)

These scenarios are **explicitly reserved** by the new contract. Each is a follow-up ADR — not in scope here.

| Future scenario | Contract supports via | Follow-up ADR |
|---|---|---|
| Streaming output (`AsyncIterator[NodeOutputChunk]`) | `port_values: Any` keeps the door open for non-pydantic types; streaming requires changing `NodeOutput` to a chunk sequence — separate ADR | Streaming output ADR |
| Dynamic plan routing (node returns next node id) | `RoutingDecision` extends with optional `goto: NodeId \| None` | Dynamic plan ADR |
| Parallel fan-out / fan-in (swarm) | `PortRegistry` is shared across plan executions | Parallel branches ADR |
| Cross-process graph (distributed execution) | `PortRegistry` already serializes to spine | Distributed graph ADR |
| Pubsub / message bus between nodes | Add `MessageBusStrategy` binding kind — port `emit(topic, msg)` typed | PubSub ADR |
| Stateful accumulator inside graph | `RoutingDecision.should_terminate` is the seed; reducer keeps owning cross-plan state | Reducer integration ADR |

The contract is **forward-compatible** with all of these. None requires breaking changes to `Predicate`, `PortRef`, `RoutingDecision`, or `NodeIOSchema`.

## 8. Acceptance criteria

1. `bundles/phase_main_outer.yaml` lifts without error
2. `lca-ops debug-graph run_<id>` shows `act.main` node entries for any run where `routing.action_type == "use_tool"`
3. `tests/integration/test_end_to_end_think_to_act.py` passes — `decision.action_type="use_tool"` routes to `act.main`
4. `tests/lca_kernel/plan/test_phase_main_outer_lift.py` passes — lift catches missing ports
5. The three known-broken predicates (current `bundles/phase_main_outer.yaml`, `bundles/declarative-phase-graph.yaml`) all become lift-time failures, not runtime false-routes
6. No `__getattr__` fallback in `lca/framework/graph/`
7. No string `when:` fields in any bundle YAML (grep verifies zero hits)
8. `grep "result.payload" lca/ lca_kernel/ bundles/` returns zero hits

## 9. Out of scope

- Streaming output (Future ADR)
- Dynamic plan routing (Future ADR)
- Parallel fan-out / fan-in (Future ADR)
- Cross-process graph (Future ADR)
- Pubsub (Future ADR)
- Reducer-side state integration changes (Reducer owns this; graph kernel doesn't grow new state sources per AGENTS.md §3 C4)
- The bug at `lca/plugins/concept/decision_enforce/chain_reject.py:90` where `gate.chain.reject` returns `degraded_from=None` — separate fix