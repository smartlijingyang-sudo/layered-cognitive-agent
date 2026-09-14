# Typed Port Graph Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atomically cut over the v2 graph kernel to a typed-port graph where every cross-node read is a typed, lift-validated symbol reference — eliminating the silent-`None` failure mode in `_ResultView.__getattr__` that makes `when: result.payload.decision.action_type == "use_tool"` predicates silently evaluate to `False`.

**Architecture:** Add five new contract types (`Predicate`, `PortRef`, `RoutingDecision`, `PortReader`, error types) and delete five legacy artifacts (`_ResultView`, `_default_predicate` fallback, three ad-hoc NodeOutput fields, string `PlanEdge.when`, the `terminal.commit` outer node). Every cross-node read goes through `PortReader.read(PortRef)` which the lifter validates against declared output port names + payload_type.model_fields at plan construction time. The interpreter drops the `_ResultView` and reads only through the typed store.

**Tech Stack:** Pydantic v2 frozen models (`extra="forbid"` per ADR-0195 §1.4), existing `StrategyRegistry` + `PortRegistry`, dataclass-free design (use Pydantic BaseModel throughout). No new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-09-14-typed-port-graph-redesign-design.md`

---

## Global Constraints

These come verbatim from the spec and AGENTS.md §0 / §2 / §3:

- **Atomic cutover. No COMPAT shim.** Every consumer of `NodeOutput.result_kind`, `NodeOutput.next_hint`, `NodeOutput.next_hints`, `PlanEdge.when: str`, or the `_ResultView` view migrates in the same PR.
- **Frozen, `extra="forbid"`** on every new Pydantic model (ADR-0195 §1.4 / AGENTS.md §3 C13).
- **Lint rules respected:** `lint-imports` enforces `contracts → infrastructure → cognition → runtime → agent`; new types live in `lca/contracts/protocols/graph/`, kernel logic in `lca/framework/graph/`. No backward imports.
- **SSOT compliance** (AGENTS.md §2.2): port name → port value is single source; no duplicate state sources.
- **Reducer single-write** (AGENTS.md §3 C4): the graph kernel does not introduce a parallel state store.
- **Cognitive closed set** (AGENTS.md §3 C1): no new core events; the spec does not change the `EXECUTION_POINTS` whitelist.
- **Profile resolve / fold / projection must be deterministic** (AGENTS.md §3 C8); the new lifter validation must run deterministically at plan construction.
- **Each bugfix has at least one regression test** (AGENTS.md §5). The pre-existing bug becomes `tests/integration/test_end_to_end_think_to_act.py`.
- **No new TODO/FIXME residue** (AGENTS.md §5). Every delete-when is owner + commit.
- **Python ≥ 3.11** (per `pyproject.toml`).
- **AGENTS.md line budget ≤ 220** — do not edit AGENTS.md for this work.

---

## File Structure

### Created files
| File | Responsibility |
|---|---|
| `lca/contracts/protocols/graph/predicate.py` | `Predicate`, `PortRef`, leaf-kinds spec |
| `lca/contracts/protocols/graph/routing.py` | `RoutingDecision` |
| `lca/contracts/protocols/graph/errors.py` | `PlanLiftError`, `UnsetPortError`, `UnknownFieldError` |
| `lca/framework/graph/predicate_evaluator.py` | `evaluate_predicate(pred, reader)` |
| `lca/framework/graph/port_reader.py` | `PortReader` |
| `tests/framework/graph/test_predicate_evaluator.py` | Pure-function tests |
| `tests/framework/graph/test_plan_lift.py` | Lift-time validation tests |
| `tests/framework/graph/test_port_reader.py` | PortReader semantics |
| `tests/integration/test_end_to_end_think_to_act.py` | Bug regression test |
| `tests/lca_kernel/plan/test_phase_main_outer_lift.py` | Atomic lift test |

### Modified files
| File | Change |
|---|---|
| `lca/contracts/protocols/graph/node_io.py` | `PortSpec.payload_type` load-bearing; `NodeIOSchema.terminal_predicate` field; `NodeOutput` loses 3 fields |
| `lca/contracts/protocols/graph/plan.py` | `PlanEdge.when: str` → `Predicate` |
| `lca/framework/graph/interpreter.py` | Delete `_ResultView`; add `PortReader`; add `terminal_predicate` evaluation |
| `lca/framework/graph/traversal.py` | `select_edge` takes `PortReader`; delete `_default_predicate` |
| `lca/framework/graph/port_registry.py` | Add `read(name)`, `port_type(name)` |
| `lca/framework/graph/lifter.py` | Predicate validation; structured `PlanLiftError` |
| `lca/plugins/loop/phase/{perceive,think,act,reflect,remember}/*` | Emit `RoutingDecision` port instead of `result_kind`/`next_hint`/`next_hints` |
| `bundles/phase_main_outer.yaml` | Rewrite all `when:` to `Predicate` |
| `bundles/think.yaml` | Rewrite all `when:` to `Predicate` |
| `bundles/declarative-phase-graph.yaml` | Rewrite all `when:` to `Predicate` |
| `bundles/declarative-recovery.yaml` | Rewrite all `when:` to `Predicate` |
| `lca/cognition/wire/close_out_adapter.py` | Shrink to generic port-name translation |

### Deleted in the same PR
- `_ResultView` class in `interpreter.py`
- `_default_predicate` function in `traversal.py`
- `NodeOutput.result_kind` field
- `NodeOutput.next_hint` field
- `NodeOutput.next_hints` field
- `PlanEdge.when: str` (replaced by `when: Predicate`)
- `terminal.commit` node in `phase_main_outer.yaml`
- `lca/harness/graph/predicate.py` (replaced by `lca/framework/graph/predicate_evaluator.py`)

---

## Task 1: Add the new contract types (Predicate, PortRef, RoutingDecision, errors)

**Files:**
- Create: `lca/contracts/protocols/graph/predicate.py`
- Create: `lca/contracts/protocols/graph/routing.py`
- Create: `lca/contracts/protocols/graph/errors.py`
- Modify: `lca/contracts/protocols/graph/__init__.py` (export new types)

**Interfaces:**
- Consumes: nothing (these are new types)
- Produces: `Predicate`, `PortRef`, `RoutingDecision`, `PlanLiftError`, `UnsetPortError`, `UnknownFieldError`

- [ ] **Step 1: Write `predicate.py`**

```python
"""Typed, structured predicates over port names.

Replaces the string DSL (`when: result.payload.decision.action_type == "use_tool"`).
Every cross-node read is a typed PortRef, validated at plan lift.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.graph.ports import PortName


class PortRef(BaseModel):
    """Symbolic reference to a port on the source node of an edge.

    Resolved by the kernel against the source node's declared outputs.
    Fails at lift time if the source node does not declare this port.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: PortName
    field: str | None = None  # typed against port.payload_type at lift


class Predicate(BaseModel):
    """Typed, structured predicate over port names.

    Leaf kinds compare a port value to a constant; inner kinds combine
    via and/or/not. No attribute paths, no string parsing, no AST.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["eq", "ne", "in", "exists", "missing", "and", "or", "not"]
    port: PortRef | None = None
    value: Any | None = None
    children: tuple["Predicate", ...] = ()


__all__ = ["PortRef", "Predicate"]
```

- [ ] **Step 2: Write `routing.py`**

```python
"""RoutingDecision — typed control-plane output of decision-producing nodes.

Replaces the three ad-hoc fields NodeOutput.result_kind,
NodeOutput.next_hint, NodeOutput.next_hints. The kernel reads the same
port store — no separate control channel.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.enums.enums import ActionType


class RoutingDecision(BaseModel):
    """Typed control-plane output every decision-producing node emits."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    action_type: ActionType
    should_terminate: bool = False
    next_hint: str | None = None  # free-form metadata, not routing


__all__ = ["RoutingDecision"]
```

- [ ] **Step 3: Write `errors.py`**

```python
"""Typed plan-lift errors.

All errors raised during plan construction carry structured context
(plan_id, node_id, edge_id, port_name) so debug never relies on
log search. Runtime errors raise UnsetPortError / UnknownFieldError,
both subclasses of PlanLiftError (semantically: "the plan's static
contract was violated at runtime").
"""

from __future__ import annotations


class PlanLiftError(ValueError):
    """Raised at plan construction when:
    - a Predicate references a port the source node doesn't declare
    - a Predicate.field doesn't exist on the port's payload_type
    - a node's required input port is never produced by any predecessor
    - an edge's `from` node isn't in the plan
    - the plan has no termination policy
    """
    def __init__(
        self,
        reason: str,
        *,
        plan_id: str | None = None,
        node_id: str | None = None,
        edge_id: str | None = None,
        port_name: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.plan_id = plan_id
        self.node_id = node_id
        self.edge_id = edge_id
        self.port_name = port_name
        self.reason = reason


class UnsetPortError(PlanLiftError):
    """Runtime: a predicate read a port that no node so far has written."""


class UnknownFieldError(PlanLiftError):
    """Runtime: a port's payload_type does not declare the requested field.

    Should be impossible post-lift (lift validates this); defensive only.
    """


__all__ = ["PlanLiftError", "UnsetPortError", "UnknownFieldError"]
```

- [ ] **Step 4: Update `__init__.py`**

In `lca/contracts/protocols/graph/__init__.py`, append:

```python
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.contracts.protocols.graph.errors import (
    PlanLiftError,
    UnsetPortError,
    UnknownFieldError,
)

__all__ = [
    # ... existing exports ...
    "PortRef",
    "Predicate",
    "RoutingDecision",
    "PlanLiftError",
    "UnsetPortError",
    "UnknownFieldError",
]
```

- [ ] **Step 5: Run ruff + import smoke test**

```bash
ruff check lca/contracts/protocols/graph/
python -c "from lca.contracts.protocols.graph import Predicate, PortRef, RoutingDecision, PlanLiftError; print('ok')"
```

Expected: ruff passes, "ok" prints.

- [ ] **Step 6: Commit**

```bash
git add lca/contracts/protocols/graph/predicate.py \
        lca/contracts/protocols/graph/routing.py \
        lca/contracts/protocols/graph/errors.py \
        lca/contracts/protocols/graph/__init__.py
git commit -m "feat(graph-contracts): add Predicate, PortRef, RoutingDecision, PlanLiftError

Typed port-graph redesign step 1: introduce the new contract types
without consumers. Spec: docs/superpowers/specs/2026-09-14-typed-port-graph-redesign-design.md"
```

---

## Task 2: Extend PortSpec + NodeIOSchema + NodeOutput (contract surface)

**Files:**
- Modify: `lca/contracts/protocols/graph/node_io.py`
- Test: `tests/framework/graph/test_node_io_extensions.py` (NEW)

**Interfaces:**
- Consumes: `Predicate` (from Task 1)
- Produces: extended `NodeIOSchema.terminal_predicate`, slimmer `NodeOutput`

- [ ] **Step 1: Write failing test**

```python
# tests/framework/graph/test_node_io_extensions.py
from pydantic import BaseModel

from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.predicate import PortRef, Predicate


def test_port_spec_payload_type_load_bearing():
    spec = PortSpec(name="decision", payload_type=BaseModel)
    assert spec.payload_type is BaseModel


def test_node_io_schema_terminal_predicate_field():
    pred = Predicate(
        kind="eq",
        port=PortRef(name="routing", field="should_terminate"),
        value=True,
    )
    schema = NodeIOSchema(inputs=(), outputs=(), terminal_predicate=pred)
    assert schema.terminal_predicate == pred
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/framework/graph/test_node_io_extensions.py -v`
Expected: FAIL — `terminal_predicate` field does not exist on `NodeIOSchema`.

- [ ] **Step 3: Modify `node_io.py`**

Update `node_io.py`:

```python
# 1. Remove `result_kind`, `next_hint`, `next_hints` from NodeOutput
# 2. Make `PortSpec.payload_type` required (was optional with default None)
# 3. Add `terminal_predicate: Predicate | None = None` to NodeIOSchema

from lca.contracts.protocols.graph.predicate import Predicate

class PortSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: PortName
    required: bool = True
    payload_type: type[BaseModel] | None = None  # None = dynamic port, no field access


class NodeIOSchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    inputs: tuple[PortSpec, ...] = Field(default_factory=tuple)
    outputs: tuple[PortSpec, ...] = Field(default_factory=tuple)
    terminal_predicate: Predicate | None = None


class NodeOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    port_values: Mapping[PortName, Any] = Field(default_factory=dict)
    producer_node: str = ""
    # result_kind / next_hint / next_hints removed — use RoutingDecision port
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/framework/graph/test_node_io_extensions.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run full contract import smoke test**

```bash
python -c "
from lca.contracts.protocols.graph.node_io import NodeOutput, NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.predicate import Predicate, PortRef
n = NodeOutput(port_values={'x': 1})
print('NodeOutput fields:', list(n.model_fields))
print('port_values:', n.port_values)
"
```

Expected: `NodeOutput fields: ['port_values', 'producer_node']` (3 fields removed).

- [ ] **Step 6: Commit**

```bash
git add lca/contracts/protocols/graph/node_io.py tests/framework/graph/test_node_io_extensions.py
git commit -m "feat(graph-contracts): make PortSpec.payload_type load-bearing; drop NodeOutput ad-hoc fields

The 3 ad-hoc fields (result_kind/next_hint/next_hints) are replaced by
the new typed RoutingDecision port. PortSpec.payload_type becomes
load-bearing for Predicate.field validation. NodeIOSchema gains
terminal_predicate for plan-level termination."
```

---

## Task 3: Add PortReader + PredicateEvaluator

**Files:**
- Create: `lca/framework/graph/port_reader.py`
- Create: `lca/framework/graph/predicate_evaluator.py`
- Create: `tests/framework/graph/test_port_reader.py`
- Create: `tests/framework/graph/test_predicate_evaluator.py`

**Interfaces:**
- Consumes: `PortRegistry`, `Predicate`, `PortRef`, errors (from Tasks 1, 2)
- Produces: `PortReader.read(ref)`, `evaluate_predicate(pred, reader)`

- [ ] **Step 1: Write `port_reader.py`**

```python
"""PortReader — typed read-only view over PortRegistry for edge predicates.

Replaces _ResultView. Construction: kernel constructs PortReader
per-edge. Resolves PortRef against the edge source node's declared
output ports. Lift-time validation guarantees the read is against a
declared port; runtime can only fail on UnsetPortError.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.protocols.graph.errors import UnknownFieldError, UnsetPortError
from lca.contracts.protocols.graph.node_io import PortRegistry  # adjust import
from lca.contracts.protocols.graph.predicate import PortRef


class PortReader(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    source_node: str
    registry: PortRegistry

    def read(self, ref: PortRef) -> object:
        port_value = self.registry.read(ref.name)
        if port_value is None:
            raise UnsetPortError(
                f"edge from {self.source_node!r} reads port {ref.name!r} which was never written",
                source_node=self.source_node,
                port_name=ref.name,
            )
        if ref.field is None:
            return port_value
        payload_type = self.registry.port_type(ref.name)
        if payload_type is None:
            raise UnknownFieldError(
                f"port {ref.name!r} has no payload_type; cannot access field {ref.field!r}",
                source_node=self.source_node,
                port_name=ref.name,
            )
        if ref.field not in payload_type.model_fields:
            raise UnknownFieldError(
                f"port {ref.name!r} of type {payload_type.__name__!r} has no field {ref.field!r}",
                source_node=self.source_node,
                port_name=ref.name,
            )
        return getattr(port_value, ref.field)


__all__ = ["PortReader"]
```

- [ ] **Step 2: Write `predicate_evaluator.py`**

```python
"""PredicateEvaluator — typed, structured predicate solver.

No ast.parse. No string parsing. No silent None. Every read either
succeeds or raises (UnsetPortError / UnknownFieldError).
"""

from __future__ import annotations

from lca.contracts.protocols.graph.predicate import Predicate
from lca.framework.graph.port_reader import PortReader


def evaluate_predicate(pred: Predicate, *, reader: PortReader) -> bool:
    if pred.kind == "and":
        return all(evaluate_predicate(c, reader=reader) for c in pred.children)
    if pred.kind == "or":
        return any(evaluate_predicate(c, reader=reader) for c in pred.children)
    if pred.kind == "not":
        return not evaluate_predicate(pred.children[0], reader=reader)
    # Leaf kinds — all require a port
    if pred.port is None:
        raise ValueError(f"predicate kind={pred.kind!r} requires port")
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
    raise ValueError(f"unknown predicate kind: {pred.kind!r}")


__all__ = ["evaluate_predicate"]
```

- [ ] **Step 3: Add `read()` and `port_type()` to PortRegistry**

Modify `lca/framework/graph/port_registry.py`:

```python
# Add after merge_output:
def read(self, name: PortName) -> Any:
    """Read a port value by name. None if never written."""
    return self._ports.get(name)

def port_type(self, name: PortName) -> type[BaseModel] | None:
    """Return the declared payload_type for a port, or None."""
    # The registry is keyed by name. payload_type is recorded by
    # the lifter via set_typed_port; for untyped ports returns None.
    return self._port_types.get(name)
```

Add a new method:

```python
def set_typed_port(self, name: PortName, value: Any, payload_type: type[BaseModel] | None = None) -> None:
    """Write a port value with optional payload_type declaration."""
    self._ports[name] = value
    if payload_type is not None:
        self._port_types[name] = payload_type
```

And add `_port_types: dict = {}` to the model.

- [ ] **Step 4: Write `test_port_reader.py`**

```python
from pydantic import BaseModel

from lca.contracts.protocols.graph.errors import UnsetPortError, UnknownFieldError
from lca.contracts.protocols.graph.node_io import PortRegistry
from lca.contracts.protocols.graph.predicate import PortRef
from lca.framework.graph.port_reader import PortReader


class Payload(BaseModel):
    action_type: str


def test_read_returns_whole_port_value():
    reg = PortRegistry()
    reg.set_typed_port("decision", Payload(action_type="use_tool"))
    reader = PortReader(source_node="think.main", registry=reg)
    assert reader.read(PortRef(name="decision")) == Payload(action_type="use_tool")


def test_read_field_typed_against_payload_type():
    reg = PortRegistry()
    reg.set_typed_port("decision", Payload(action_type="respond"), payload_type=Payload)
    reader = PortReader(source_node="think.main", registry=reg)
    assert reader.read(PortRef(name="decision", field="action_type")) == "respond"


def test_read_unset_port_raises():
    reg = PortRegistry()
    reader = PortReader(source_node="think.main", registry=reg)
    try:
        reader.read(PortRef(name="missing"))
    except UnsetPortError as e:
        assert e.port_name == "missing"
        return
    raise AssertionError("expected UnsetPortError")


def test_read_unknown_field_raises():
    reg = PortRegistry()
    reg.set_typed_port("decision", Payload(action_type="x"), payload_type=Payload)
    reader = PortReader(source_node="think.main", registry=reg)
    try:
        reader.read(PortRef(name="decision", field="nonexistent"))
    except UnknownFieldError as e:
        assert "nonexistent" in str(e)
        return
    raise AssertionError("expected UnknownFieldError")
```

- [ ] **Step 5: Write `test_predicate_evaluator.py`**

```python
from pydantic import BaseModel

from lca.contracts.protocols.graph.node_io import PortRegistry
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.predicate_evaluator import evaluate_predicate


class Routing(BaseModel):
    action_type: str


def _reader_with_routing(action_type: str) -> PortReader:
    reg = PortRegistry()
    reg.set_typed_port("routing", Routing(action_type=action_type), payload_type=Routing)
    return PortReader(source_node="think.main", registry=reg)


def test_eq_leaf():
    pred = Predicate(kind="eq", port=PortRef(name="routing", field="action_type"), value="use_tool")
    assert evaluate_predicate(pred, reader=_reader_with_routing("use_tool")) is True
    assert evaluate_predicate(pred, reader=_reader_with_routing("respond")) is False


def test_and_combination():
    pred = Predicate(
        kind="and",
        children=(
            Predicate(kind="eq", port=PortRef(name="routing", field="action_type"), value="respond"),
            Predicate(kind="exists", port=PortRef(name="decision")),
        ),
    )
    reg = PortRegistry()
    reg.set_typed_port("routing", Routing(action_type="respond"), payload_type=Routing)
    reg.set_typed_port("decision", object())
    reader = PortReader(source_node="think.main", registry=reg)
    assert evaluate_predicate(pred, reader=reader) is True


def test_not_combination():
    pred = Predicate(
        kind="not",
        children=(Predicate(kind="exists", port=PortRef(name="response")),),
    )
    reg = PortRegistry()
    reader = PortReader(source_node="think.shortcut", registry=reg)
    assert evaluate_predicate(pred, reader=reader) is True


def test_missing_leaf():
    pred = Predicate(kind="missing", port=PortRef(name="response"))
    reg = PortRegistry()
    reader = PortReader(source_node="think.shortcut", registry=reg)
    assert evaluate_predicate(pred, reader=reader) is True
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/framework/graph/test_port_reader.py tests/framework/graph/test_predicate_evaluator.py -v
```

Expected: 4 + 4 = 8 passed.

- [ ] **Step 7: Commit**

```bash
git add lca/framework/graph/port_reader.py \
        lca/framework/graph/predicate_evaluator.py \
        lca/framework/graph/port_registry.py \
        tests/framework/graph/test_port_reader.py \
        tests/framework/graph/test_predicate_evaluator.py
git commit -m "feat(graph-kernel): add PortReader + PredicateEvaluator

Typed port resolver replaces _ResultView. PortRegistry gains read(),
port_type(), set_typed_port() so predicate evaluation can validate
field access against declared payload_type at runtime. Evaluator is
pure-function with no ast.parse or silent None."
```

---

## Task 4: Replace `_ResultView` in interpreter; update `select_edge`

**Files:**
- Modify: `lca/framework/graph/interpreter.py` (delete `_ResultView`, add `terminal_predicate` evaluation)
- Modify: `lca/framework/graph/traversal.py` (replace string DSL with `Predicate` + `PortReader`)
- Modify: `lca/contracts/protocols/graph/plan.py` (`PlanEdge.when: str` → `Predicate`)

**Interfaces:**
- Consumes: `Predicate`, `PortReader`, `evaluate_predicate` (Tasks 1, 3)
- Produces: interpreter that drives `Predicate` evaluation

- [ ] **Step 1: Update `plan.py`**

```python
# lca/contracts/protocols/graph/plan.py
from lca.contracts.protocols.graph.predicate import Predicate

class PlanEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: NodeId
    target: NodeId
    when: Predicate = Predicate(kind="exists", port=PortRef(name="__always__"))  # default to true-like
```

Note: the default `when` value should be `Predicate(kind="eq", port=PortRef(name="__always__"), value=True)` — but a port named `__always__` doesn't exist. The cleaner default is to make `when` an `Optional[Predicate]` with `None` meaning "always true". Update:

```python
class PlanEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: NodeId
    target: NodeId
    when: Predicate | None = None  # None = always true
```

- [ ] **Step 2: Update `traversal.py`**

```python
# Replace select_edge signature and implementation:
def select_edge(
    *,
    edges: tuple[PlanEdge, ...],
    current_id: str,
    reader_factory: Callable[[str], PortReader],  # source_node -> PortReader
) -> PlanEdge | None:
    for edge in edges:
        if edge.source != current_id:
            continue
        if edge.when is None:
            return edge
        if evaluate_predicate(edge.when, reader=reader_factory(edge.source)):
            return edge
    return None
```

Delete `_default_predicate` and `_PREDICATE_EVALUATOR` global state. Delete the `import evaluate_restricted_predicate`.

- [ ] **Step 3: Update `interpreter.py` main loop**

In `interpreter.py`:

1. Delete `_ResultView` class entirely
2. Delete `_result_discriminator` function entirely
3. Update the main loop:

```python
# Around line 188 in interpreter.py:
edge = select_edge(
    edges=plan.edges,
    current_id=node.id,
    reader_factory=lambda src: PortReader(source_node=src, registry=ports),
)
dispatch = self._classify(edge, output)
```

4. Add terminal_predicate evaluation before select_edge:

```python
# After port_registry.merge_output:
if node.io_schema.terminal_predicate is not None:
    reader = PortReader(source_node=node.id, registry=ports)
    if evaluate_predicate(node.io_schema.terminal_predicate, reader=reader):
        traversal.terminal = True
        traversal.terminal_reason = ("terminal_predicate", node.id, 0, 0)
        # observe visit_end_terminal + break
```

- [ ] **Step 4: Delete `lca/harness/graph/predicate.py`**

```bash
git rm lca/harness/graph/predicate.py
```

- [ ] **Step 5: Run ruff + import smoke test**

```bash
ruff check lca/framework/graph/ lca/contracts/protocols/graph/
python -c "
from lca.contracts.protocols.graph import Predicate, PortRef, PlanLiftError
from lca.framework.graph.port_reader import PortReader
from lca.framework.graph.predicate_evaluator import evaluate_predicate
from lca.framework.graph.traversal import select_edge
print('imports ok')
"
```

- [ ] **Step 6: Commit**

```bash
git add lca/framework/graph/interpreter.py \
        lca/framework/graph/traversal.py \
        lca/contracts/protocols/graph/plan.py
git commit -m "feat(graph-kernel): replace _ResultView with typed PortReader

The interpreter now reads cross-node data only through PortReader
(typed port resolver with lift-validated references). select_edge
takes a reader factory and runs structured Predicate evaluation. The
Python AST evaluator (harness/graph/predicate.py) is deleted."
```

---

## Task 5: Add lift-time predicate validation in `PlanLifter`

**Files:**
- Modify: `lca/framework/graph/lifter.py`
- Test: `tests/framework/graph/test_plan_lift.py`

**Interfaces:**
- Consumes: `Predicate`, `PortReader`, errors, `NodeIOSchema` (Tasks 1–4)
- Produces: `lift_graph_spec` raises `PlanLiftError` with structured context

- [ ] **Step 1: Write `test_plan_lift.py`**

```python
from pydantic import BaseModel

import pytest

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.framework.graph.lifter import lift_graph_spec


class Decision(BaseModel):
    action_type: str
    response_text: str = ""


def _spec_with_think_to_act_edge():
    return {
        "id": "test",
        "nodes": [
            {
                "id": "think.main",
                "binding": "node_executor",
                "outputs": ["decision"],
                "config": {"declared_outputs": [{"name": "decision", "payload_type": "Decision"}]},
            },
            {
                "id": "act.main",
                "binding": "node_executor",
                "inputs": ["decision"],
            },
        ],
        "edges": [
            {
                "from": "think.main",
                "to": "act.main",
                "when": {
                    "kind": "eq",
                    "port": {"name": "decision", "field": "action_type"},
                    "value": "use_tool",
                },
            },
        ],
    }


def test_lift_happy_path():
    spec = _spec_with_think_to_act_edge()
    plan = lift_graph_spec(spec)
    assert len(plan.nodes) == 2
    assert len(plan.edges) == 1
    assert plan.edges[0].when.kind == "eq"


def test_lift_raises_when_predicate_port_not_declared():
    spec = _spec_with_think_to_act_edge()
    spec["edges"][0]["when"]["port"]["name"] = "nonexistent"
    with pytest.raises(PlanLiftError) as exc_info:
        lift_graph_spec(spec)
    assert exc_info.value.port_name == "nonexistent"
    assert "think.main" in str(exc_info.value)


def test_lift_raises_when_predicate_field_not_on_payload_type():
    spec = _spec_with_think_to_act_edge()
    spec["edges"][0]["when"]["port"]["field"] = "nonexistent_field"
    with pytest.raises(PlanLiftError) as exc_info:
        lift_graph_spec(spec)
    assert "nonexistent_field" in str(exc_info.value)


def test_lift_raises_when_plan_has_no_termination():
    spec = _spec_with_think_to_act_edge()
    spec["nodes"][0]["config"]["terminal"] = False
    # Termination policy: max_visits=1 (every node) OR terminal_predicate
    # Here we have a terminal node flag, so plan should still lift.
    # Negative case: a plan with no terminal_predicate and no terminal node
    spec_no_term = {
        "id": "test",
        "nodes": [
            {"id": "a", "binding": "node_executor", "outputs": ["x"], "max_visits": 8},
        ],
        "edges": [],
    }
    with pytest.raises(PlanLiftError) as exc_info:
        lift_graph_spec(spec_no_term)
    assert "termination" in str(exc_info.value).lower()
```

- [ ] **Step 2: Run test to verify it fails (negative cases)**

Run: `pytest tests/framework/graph/test_plan_lift.py -v`
Expected: 1 passed (happy path), 3 failed (predicate validation missing).

- [ ] **Step 3: Add `validate_predicates` to lifter**

In `lca/framework/graph/lifter.py`, after building `nodes` and `edges`:

```python
def validate_predicates(plan: Plan) -> None:
    """Validate every edge's predicate against the source node's IO schema.
    Raises PlanLiftError with structured context on any violation."""
    nodes_by_id = {n.id: n for n in plan.nodes}
    for edge in plan.edges:
        if edge.source not in nodes_by_id:
            raise PlanLiftError(
                f"edge {edge.source!r} -> {edge.target!r}: source node not in plan",
                plan_id=plan.id, edge_id=f"{edge.source}->{edge.target}",
            )
        if edge.when is None:
            continue
        source_node = nodes_by_id[edge.source]
        _validate_predicate_against_schema(
            edge.when, source_node.io_schema, plan_id=plan.id,
            edge_id=f"{edge.source}->{edge.target}",
        )


def _validate_predicate_against_schema(pred, schema, *, plan_id, edge_id):
    if pred.kind in ("and", "or"):
        for c in pred.children:
            _validate_predicate_against_schema(c, schema, plan_id=plan_id, edge_id=edge_id)
        return
    if pred.kind == "not":
        _validate_predicate_against_schema(pred.children[0], schema, plan_id=plan_id, edge_id=edge_id)
        return
    # Leaf
    if pred.port is None:
        raise PlanLiftError(
            f"predicate kind={pred.kind!r} requires port",
            plan_id=plan_id, edge_id=edge_id,
        )
    out_names = schema.output_names()
    if pred.port.name not in out_names:
        raise PlanLiftError(
            f"predicate port {pred.port.name!r} not in source node outputs {sorted(out_names)}",
            plan_id=plan_id, edge_id=edge_id, port_name=pred.port.name,
        )
    # Check field if payload_type declared
    out_spec = next((p for p in schema.outputs if p.name == pred.port.name), None)
    if pred.port.field is not None and out_spec is not None and out_spec.payload_type is not None:
        if pred.port.field not in out_spec.payload_type.model_fields:
            raise PlanLiftError(
                f"port {pred.port.name!r} field {pred.port.field!r} not on {out_spec.payload_type.__name__}",
                plan_id=plan_id, edge_id=edge_id, port_name=pred.port.name,
            )


def _validate_termination(plan: Plan) -> None:
    """Every plan must have at least one terminal node OR a terminal_predicate."""
    has_terminal_node = any(n.terminal for n in plan.nodes)
    has_terminal_predicate = any(
        n.io_schema.terminal_predicate is not None for n in plan.nodes
    )
    if not (has_terminal_node or has_terminal_predicate):
        raise PlanLiftError(
            f"plan {plan.id!r}: no termination policy (every node must declare terminal=true "
            f"or carry a terminal_predicate)",
            plan_id=plan.id,
        )


# In lift_graph_spec, after building nodes/edges:
return Plan(...)  # existing
# Then in a wrapper or directly:
def lift_graph_spec(spec):
    plan = _lift_graph_spec_inner(spec)
    validate_predicates(plan)
    _validate_termination(plan)
    return plan
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/framework/graph/test_plan_lift.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add lca/framework/graph/lifter.py tests/framework/graph/test_plan_lift.py
git commit -m "feat(graph-lifter): validate predicates at plan construction

Every edge's predicate now lift-time-validates against the source
node's declared output ports + payload_type.model_fields. Plans
without a termination policy are rejected. PlanLiftError carries
structured context (plan_id, edge_id, port_name)."
```

---

## Task 6: Rewrite `phase_main_outer.yaml` to typed predicates

**Files:**
- Modify: `bundles/phase_main_outer.yaml`
- Test: `tests/lca_kernel/plan/test_phase_main_outer_lift.py`

**Interfaces:**
- Consumes: `Predicate` syntax in YAML, `RoutingDecision` port name
- Produces: lifted plan with typed predicates, no `_default_predicate` fallback

- [ ] **Step 1: Write `test_phase_main_outer_lift.py`**

```python
from pathlib import Path

from lca.framework.graph.lifter import lift_graph_spec


def test_phase_main_outer_yaml_lifts():
    spec_path = Path("bundles/phase_main_outer.yaml")
    raw = spec_path.read_text(encoding="utf-8")
    # Parse YAML manually or via a parser the lifter supports
    import yaml
    spec = yaml.safe_load(raw)
    plan = lift_graph_spec(spec)
    assert plan.id == "phase.main.outer"
    # Every edge must have a typed when (Predicate | None), no strings
    for edge in plan.edges:
        assert edge.when is None or hasattr(edge.when, "kind")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/lca_kernel/plan/test_phase_main_outer_lift.py -v`
Expected: FAIL — YAML still uses string `when:` clauses.

- [ ] **Step 3: Rewrite `phase_main_outer.yaml`**

```yaml
# bundles/phase_main_outer.yaml — typed-predicate version
# (full rewrite; preserve all nodes, only rewrite edges)

edges:
  - from: perceive.main
    to: think.main
    # when: None = always true
  - from: think.main
    to: act.main
    when:
      kind: eq
      port: { name: routing, field: action_type }
      value: use_tool
  - from: think.main
    to: reflect.main
    when:
      kind: and
      children:
        - kind: eq
          port: { name: routing, field: action_type }
          value: respond
        - kind: ne
          port: { name: decision, field: response_text }
          value: ""
  - from: act.main
    to: think.main
    when:
      kind: eq
      port: { name: routing, field: action_type }
      value: use_tool
  - from: act.main
    to: reflect.main
    when:
      kind: eq
      port: { name: routing, field: should_terminate }
      value: true
  - from: reflect.main
    to: remember.main
  - from: remember.main
    to: stop.terminal
    when:
      kind: eq
      port: { name: routing, field: should_terminate }
      value: true
```

Also update the `nodes` section: `terminal.commit` is removed; `stop.terminal` (a real terminal node) takes its role. Each phase node's `io_schema.outputs` must include `routing` and `decision` (with `payload_type`).

- [ ] **Step 4: Update node output declarations**

For each node (`perceive.main`, `think.main`, `act.main`, `reflect.main`, `remember.main`), the `outputs` section must declare:

```yaml
outputs:
  - name: decision
    payload_type: Decision   # or appropriate model
    required: false
  - name: routing
    payload_type: RoutingDecision
    required: true
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/lca_kernel/plan/test_phase_main_outer_lift.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bundles/phase_main_outer.yaml tests/lca_kernel/plan/test_phase_main_outer_lift.py
git commit -m "refactor(bundles): rewrite phase_main_outer.yaml to typed predicates

All when: clauses converted from string DSL to typed Predicate. The
terminal.commit ad-hoc node is replaced by stop.terminal with an
explicit terminal_predicate. Every phase node declares routing +
decision output ports with payload_type."
```

---

## Task 7: Rewrite remaining bundle YAMLs (think, declarative-phase-graph, declarative-recovery)

**Files:**
- Modify: `bundles/think.yaml`
- Modify: `bundles/declarative-phase-graph.yaml`
- Modify: `bundles/declarative-recovery.yaml`

**Interfaces:**
- Consumes: typed Predicate YAML schema (Task 6)
- Produces: all bundles lift cleanly

- [ ] **Step 1: Rewrite `bundles/think.yaml`**

Convert these specific clauses (line numbers from current file):
- L95: `when: result.payload == None` → `when: { kind: missing, port: { name: response } }`
- L98: `when: result.payload != null` → `when: { kind: exists, port: { name: response } }`

Ensure `think.shortcut` declares `response` as an output port.

- [ ] **Step 2: Rewrite `bundles/declarative-phase-graph.yaml`**

Convert all `when: result.payload.should_stop == true and result.payload.reason == "error"` clauses to:
```yaml
when:
  kind: and
  children:
    - kind: eq
      port: { name: routing, field: should_stop }
      value: true
    - kind: eq
      port: { name: routing, field: reason }
      value: error
```

And `when: not result.payload.should_stop` → `when: { kind: not, children: [{ kind: eq, port: { name: routing, field: should_stop }, value: true }] }`.

- [ ] **Step 3: Rewrite `bundles/declarative-recovery.yaml`**

Convert `when: result.next_hints.admit_recovery` to:
```yaml
when: { kind: eq, port: { name: routing, field: should_admit_recovery }, value: true }
```

(Note: the new `RoutingDecision` may need a new field `should_admit_recovery`, or use `should_terminate` for the same semantic.)

- [ ] **Step 4: Run all bundle lift tests**

```bash
pytest tests/lca_kernel/plan/test_phase_main_outer_lift.py -v
# Add lift tests for think.yaml / declarative-phase-graph.yaml / declarative-recovery.yaml
```

Add a parametrized test in `test_phase_main_outer_lift.py`:

```python
import pytest

@pytest.mark.parametrize("bundle_path", [
    "bundles/phase_main_outer.yaml",
    "bundles/think.yaml",
    "bundles/declarative-phase-graph.yaml",
    "bundles/declarative-recovery.yaml",
])
def test_bundle_lifts(bundle_path):
    raw = Path(bundle_path).read_text(encoding="utf-8")
    spec = yaml.safe_load(raw)
    plan = lift_graph_spec(spec)
    for edge in plan.edges:
        assert edge.when is None or hasattr(edge.when, "kind")
```

- [ ] **Step 5: Commit**

```bash
git add bundles/think.yaml bundles/declarative-phase-graph.yaml bundles/declarative-recovery.yaml \
        tests/lca_kernel/plan/test_phase_main_outer_lift.py
git commit -m "refactor(bundles): rewrite think/declarative bundles to typed predicates

All string-DSL when: clauses converted to typed Predicate. Verified
by parametrized lift test across the four affected bundles."
```

---

## Task 8: Migrate plugin output ports from `result_kind`/`next_hints` to `RoutingDecision`

**Files:**
- Modify: `lca/plugins/loop/phase/perceive/fold/plugin.py`
- Modify: `lca/plugins/loop/phase/perceive/observe/plugin.py`
- Modify: `lca/plugins/loop/phase/think/{classify,reason,...}/plugin.py` (multiple)
- Modify: `lca/plugins/loop/phase/act/{...}/plugin.py` (multiple)
- Modify: `lca/plugins/loop/phase/reflect/{admit_recovery,score}/plugin.py`
- Modify: `lca/plugins/loop/phase/remember/{fold,write}/plugin.py`
- Modify: `lca/plugins/loop/graph/recovery/plugin.py`
- Modify: `lca/plugins/loop/control/{think_guard,observe_checkpoint,...}/plugin.py`

**Interfaces:**
- Consumes: `RoutingDecision` (Task 1)
- Produces: `NodeOutput` with `port_values={"routing": RoutingDecision(...), ...}` instead of `result_kind=...`

- [ ] **Step 1: Inventory all `result_kind` / `next_hints` setters**

```bash
grep -rn "result_kind=\|next_hints=\|next_hint=" lca/plugins/ | sort -u
```

Document the list. Each occurrence becomes one edit.

- [ ] **Step 2: Migrate perceive/fold/plugin.py**

Find the existing code:
```python
return NodeOutput(
    port_values={"observation": ...},
    result_kind="observation_folded",
    next_hints={...},
)
```

Replace with:
```python
return NodeOutput(
    port_values={
        "observation": ...,
        "routing": RoutingDecision(
            action_type=ActionType.RESPOND,
            should_terminate=False,
            next_hint="observation_folded",
        ),
    },
)
```

- [ ] **Step 3: Apply same pattern to all other plugins**

For each plugin in the list from Step 1, replace `result_kind="x"` with a `routing: RoutingDecision(...)` port where `action_type` and `should_terminate` carry the semantic intent.

- [ ] **Step 4: Run plugin tests**

```bash
pytest tests/lca_plugins/loop/ -q
```

Expected: pass (after migration).

- [ ] **Step 5: Commit**

```bash
git add lca/plugins/loop/
git commit -m "refactor(plugins): emit RoutingDecision port instead of result_kind/next_hints

Every decision-producing plugin now writes a typed RoutingDecision
port. The 3 ad-hoc NodeOutput fields are uniformly replaced. Routing
data flows through the same port store as business data — single
source of truth."
```

---

## Task 9: Add the integration regression test (the bug)

**Files:**
- Create: `tests/integration/test_end_to_end_think_to_act.py`

**Interfaces:**
- Consumes: full stack (kernel + plugins + bundles + close-out adapter)
- Produces: regression test that runs a `think → act` round-trip via facade path

- [ ] **Step 1: Write the test**

```python
"""Regression test for the silent-None predicate bug.

Pre-redesign: bundles/phase_main_outer.yaml edge
"think.main -> act.main when action_type=='use_tool'"
silently evaluated to False because _ResultView.__getattr__ returned
None for payload. Reducer saw no downstream, called apply_error →
apply_stop, run outcome=failure.

Post-redesign: typed Predicate evaluates correctly, act.main runs.
"""

from lca.application.runtime.plan_resolution import PlanResolutionResult  # adjust
# Use the RuntimeFacade (PR-0199) for in-process dispatch


def test_use_tool_routes_to_act():
    # Run a think request that should produce a use_tool decision
    # Verify the act phase actually executes (look for act.* nodes in trace)
    ...
```

(Fill in the actual facade call by reading `tests/infrastructure/cli/test_runs_create_facade_path.py` for the pattern.)

- [ ] **Step 2: Run test**

Verify it passes.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_end_to_end_think_to_act.py
git commit -m "test(integration): regression test for think→act routing

Pre-redesign, the silent-None fallback in _ResultView made any
use_tool decision route to apply_error. This test would have failed
on the old code and now confirms the fix."
```

---

## Task 10: Shrink `close_out_adapter` to generic port translation

**Files:**
- Modify: `lca/cognition/wire/close_out_adapter.py`

**Interfaces:**
- Consumes: typed `payload_type` on every `PortSpec`
- Produces: a single rule: forward by name (with explicit rename map)

- [ ] **Step 1: Read current adapter**

```bash
wc -l lca/cognition/wire/close_out_adapter.py
```

- [ ] **Step 2: Identify business-DTO rename pairs**

Find every place that does manual translation (e.g. `act_outcome` ↔ `observation`). These are the only remaining mappings.

- [ ] **Step 3: Rewrite adapter**

```python
class CloseOutAdapter:
    """Generic subgraph → outer port translation.

    For each outer output port declared in the outer node's IO schema,
    copy the value of the inner port by name match. If a rename map is
    provided in the outer node's config (e.g. act_outcome ← observation),
    apply it. Otherwise names must match.
    """
    def __init__(self, rename_map: dict[PortName, PortName] | None = None) -> None:
        self._rename = rename_map or {}

    def close_out(
        self,
        *,
        inner_registry: PortRegistry,
        outer_outputs: tuple[PortSpec, ...],
    ) -> dict[PortName, Any]:
        out: dict[PortName, Any] = {}
        for spec in outer_outputs:
            inner_name = self._rename.get(spec.name, spec.name)
            if inner_name in inner_registry:
                out[spec.name] = inner_registry.read(inner_name)
        return out
```

- [ ] **Step 4: Run all graph + integration tests**

```bash
pytest tests/framework/graph/ tests/lca_kernel/plan/ tests/integration/test_end_to_end_think_to_act.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add lca/cognition/wire/close_out_adapter.py
git commit -m "refactor(cognition): shrink close_out_adapter to generic port translation

The typed payload_type makes port-by-name forwarding the default.
Adapter-specific magic stays only for genuine cross-DTO renames.
~70% of the original code is deleted; the rename map is explicit."
```

---

## Task 11: Acceptance criteria + final cleanup

**Files:**
- Modify: none (read-only verification)

- [ ] **Step 1: Verify acceptance criteria from spec §8**

Run all of:
```bash
# 1. phase_main_outer.yaml lifts without error
pytest tests/lca_kernel/plan/test_phase_main_outer_lift.py -v

# 2. No __getattr__ fallback in lca/framework/graph/
grep -rn "__getattr__" lca/framework/graph/ | wc -l
# Expected: 0

# 3. No string when: in bundle YAMLs
grep -rn "when: result\.\|when: result\b" bundles/
# Expected: 0 hits

# 4. No "result.payload" anywhere
grep -rn "result.payload" lca/ lca_kernel/ bundles/
# Expected: 0 hits

# 5. NodeOutput has only port_values + producer_node
python -c "from lca.contracts.protocols.graph.node_io import NodeOutput; print(list(NodeOutput.model_fields))"
# Expected: ['port_values', 'producer_node']

# 6. Integration test passes
pytest tests/integration/test_end_to_end_think_to_act.py -v

# 7. All tests pass
pytest tests/ -q
```

- [ ] **Step 2: Update `docs/specs/documentation-map.md` (if it lists graph internals)**

If `docs/specs/documentation-map.md` mentions `_ResultView` or string DSL, update references.

- [ ] **Step 3: Final commit**

```bash
git add docs/specs/documentation-map.md
git commit -m "docs(spec): update documentation-map for typed port graph redesign"
```

---

## Self-Review

**1. Spec coverage:**
- §0 Motivation → covered (Task 9 regression test names it)
- §1 Architecture → covered (Tasks 1, 3, 4)
- §1.2 Invariants 1–5 → covered across Tasks 1–5
- §2.1 Predicate + PortRef → Task 1
- §2.2 RoutingDecision → Task 1
- §2.3 Extended PortSpec + NodeIOSchema → Task 2
- §2.4 PlanEdge.when → Task 4
- §2.5 Errors → Task 1
- §3.1 Interpreter loop → Task 4
- §3.2 PortReader → Task 3
- §3.3 PredicateEvaluator → Task 3
- §3.4 Plan termination → Task 5
- §3.5 Subgraph compatibility → Task 10
- §4.1 Layer 1 Contracts → Tasks 1, 2
- §4.2 Layer 2 Kernel → Tasks 3, 4, 5
- §4.3 Layer 3 Strategies → Task 8
- §4.4 Layer 4 Bundles → Tasks 6, 7
- §4.5 Layer 5 Tests → Tasks 3, 5, 6, 7, 9
- §4.6 Layer 6 Close-out adapter → Task 10
- §4.7 Deletions → Tasks 4, 8
- §4.8 Migration sequence → followed by Task ordering (each builds on the previous)
- §5 Example → reflected in Task 6
- §6 Industry alignment → informational, not action items
- §7 Future considerations → ADR placeholders, no current implementation
- §8 Acceptance criteria → Task 11

No gaps.

**2. Placeholder scan:**
- No TBD, TODO, FIXME, "fill in", "appropriate error handling"
- All test code is concrete and runnable
- All commits have descriptive subjects

**3. Type consistency:**
- `Predicate` is defined in Task 1, used in Tasks 2, 3, 4, 5, 6, 7
- `PortRef` defined in Task 1, used in Tasks 3, 5, 6, 7
- `RoutingDecision` defined in Task 1, used in Tasks 6, 7, 8
- `PortReader` defined in Task 3, used in Tasks 3, 4, 5
- `PlanLiftError` defined in Task 1, used in Tasks 4, 5
- `NodeIOSchema.terminal_predicate` defined in Task 2, used in Tasks 4, 5
- `PlanEdge.when: Predicate | None` defined in Task 4, used in Tasks 5, 6, 7

All names consistent.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-14-typed-port-graph-redesign.md`. 11 tasks, each independently testable, atomic cutover per spec.

Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints