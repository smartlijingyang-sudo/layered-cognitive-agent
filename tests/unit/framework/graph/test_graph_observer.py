"""Tests for the kernel-side graph observation seam.

What this verifies:

- ``PlanInterpreter`` emits one observation per lifecycle stage
  (visit start, visit end, edge) for a fresh plan traversal.
- ``SpineGraphObserver`` translates observations into EP+payload
  calls against the injected ``emit`` callable.
- ``GraphEpTable`` is the single point of EP-name control and can
  be swapped without touching the kernel.
- Every payload carries the full :class:`GraphObservation` field
  set; nothing is silently filtered.
- ``SubgraphStrategy`` emits enter / exit around the recursive
  runner, and exception during recursion still produces an exit
  observation with ``outcome="failure"``.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
)
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.strategy import (
    NodeStrategy,
    StrategyContext,
)
from lca.framework.graph.ep_table import (
    EP_EDGE_TRANSIT,
    EP_NODE_END,
    EP_NODE_START,
    EP_SUBGRAPH_ENTER,
    EP_SUBGRAPH_EXIT,
    GraphEpTable,
)
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.observation import (
    KIND_EDGE,
    KIND_SUBGRAPH_ENTER,
    KIND_SUBGRAPH_EXIT,
    KIND_VISIT_END,
    KIND_VISIT_START,
    GraphObservation,
    NullGraphObserver,
    payload_of,
)
from lca.framework.graph.observer_impls import (
    RecordingObserver,
    SpineGraphObserver,
)
from lca.framework.graph.strategy_registry import StrategyRegistry


def _make_stub(*, emit: dict[PortName, object], next_target: str | None = None) -> NodeStrategy:
    """Build a stub :class:`NodeStrategy` with deterministic outputs."""

    class _Stub:
        kind = BindingKind.NODE_EXECUTOR
        schema = NodeIOSchema()

        async def execute(self, context, input):  # type: ignore[override]
            return NodeOutput(
                port_values=dict(emit),
                producer_node=context.node_id,
                result_kind="decision",
                next_hints={"next": next_target or ""},
            )

    return _Stub()


def _make_plan() -> Plan:
    a = PlanNode(
        id="a",
        binding=BindingKind.NODE_EXECUTOR,
        io_schema=NodeIOSchema(),
        config={"purpose": "first", "region": "phase:think"},
        entry=True,
    )
    b = PlanNode(
        id="b",
        binding=BindingKind.NODE_EXECUTOR,
        io_schema=NodeIOSchema(),
        config={"purpose": "second", "region": "phase:think"},
        terminal=True,
    )
    edge = PlanEdge(source="a", target="b")
    return Plan(id="p1", nodes=(a, b), edges=(edge,))


def _make_registry(strategy: NodeStrategy) -> StrategyRegistry:
    reg = StrategyRegistry()
    reg.register(strategy)
    return reg


def _stub_registry(
    emit: dict[PortName, object], next_target: str | None = None
) -> StrategyRegistry:
    return _make_registry(_make_stub(emit=emit, next_target=next_target))


def test_observation_payload_carries_every_field() -> None:
    obs = GraphObservation(
        kind=KIND_VISIT_END,
        plan_ref="p1",
        occurred_at_ms=42,
        node_id="a",
        node_index=1,
        depth=2,
        binding="NODE_EXECUTOR",
        dispatch="next",
        outcome="success",
        elapsed_ms=17,
        inputs=(("turn_plan", {"x": 1}),),
        outputs=(("decision", {"a": "b"}),),
        metadata=(("binding", "NODE_EXECUTOR"), ("max_visits", 1)),
    )
    payload = payload_of(obs)
    assert payload["kind"] == KIND_VISIT_END
    assert payload["plan_ref"] == "p1"
    assert payload["occurred_at_ms"] == 42
    assert payload["node_id"] == "a"
    assert payload["node_index"] == 1
    assert payload["depth"] == 2
    assert payload["binding"] == "NODE_EXECUTOR"
    assert payload["dispatch"] == "next"
    assert payload["outcome"] == "success"
    assert payload["error"] == ""
    assert payload["elapsed_ms"] == 17
    assert payload["inputs"] == {"turn_plan": {"x": 1}}
    assert payload["outputs"] == {"decision": {"a": "b"}}
    assert payload["metadata"] == {"binding": "NODE_EXECUTOR", "max_visits": 1}


def test_null_observer_is_default_and_records_nothing() -> None:
    interp = PlanInterpreter(registry=_stub_registry({}, next_target="b"))
    assert isinstance(interp.observer, NullGraphObserver)
    import asyncio

    asyncio.run(interp.run(_make_plan()))
    assert interp.recorder.all()


@pytest.mark.asyncio
async def test_kernel_emits_start_end_edge_for_two_node_plan() -> None:
    rec = RecordingObserver()
    interp = PlanInterpreter(
        registry=_stub_registry({"decision": "ok"}, next_target="b"),
        observer=rec,
    )
    await interp.run(_make_plan())
    kinds = [e.kind for e in rec.events]
    assert kinds.count(KIND_VISIT_START) == 2
    assert kinds.count(KIND_VISIT_END) == 2
    assert kinds.count(KIND_EDGE) == 1
    starts = rec.by_kind(KIND_VISIT_START)
    assert [e.node_id for e in starts] == ["a", "b"]
    end_a = next(e for e in rec.events if e.kind == KIND_VISIT_END and e.node_id == "a")
    assert end_a.outcome == "success"
    assert end_a.elapsed_ms >= 0
    assert end_a.outputs == (("decision", "ok"),)
    edge = next(e for e in rec.events if e.kind == KIND_EDGE)
    assert edge.from_node == "a"
    assert edge.to_node == "b"
    assert edge.edge_id == "a->b"
    assert edge.metadata == (("when", "true"),)


def test_spine_observer_resolves_default_table() -> None:
    emitted: list[tuple[str, dict]] = []

    def emit(ep, payload):
        emitted.append((ep, payload))

    obs = SpineGraphObserver(emit=emit)
    obs.observe(
        GraphObservation(
            kind=KIND_VISIT_START,
            plan_ref="p",
            occurred_at_ms=1,
            node_id="a",
        )
    )
    obs.observe(
        GraphObservation(
            kind=KIND_VISIT_END,
            plan_ref="p",
            occurred_at_ms=2,
            node_id="a",
            outcome="success",
        )
    )
    obs.observe(
        GraphObservation(
            kind=KIND_EDGE,
            plan_ref="p",
            occurred_at_ms=3,
            edge_id="e1",
            from_node="a",
            to_node="b",
        )
    )
    obs.observe(
        GraphObservation(
            kind=KIND_SUBGRAPH_ENTER,
            plan_ref="p",
            occurred_at_ms=4,
        )
    )
    obs.observe(
        GraphObservation(
            kind=KIND_SUBGRAPH_EXIT,
            plan_ref="p",
            occurred_at_ms=5,
            outcome="success",
        )
    )
    assert [ep for ep, _ in emitted] == [
        EP_NODE_START,
        EP_NODE_END,
        EP_EDGE_TRANSIT,
        EP_SUBGRAPH_ENTER,
        EP_SUBGRAPH_EXIT,
    ]
    for _, payload in emitted:
        assert payload["plan_ref"] == "p"


def test_spine_observer_uses_replaced_table() -> None:
    """Profiles can override the EP table without touching the kernel."""
    emitted: list[str] = []
    custom = GraphEpTable(
        visit_start="custom.visit",
        visit_end="custom.end",
        edge="custom.edge",
        subgraph_enter="custom.sub.in",
        subgraph_exit="custom.sub.out",
    )
    obs = SpineGraphObserver(ep_table=custom, emit=lambda ep, _p: emitted.append(ep))
    obs.observe(
        GraphObservation(kind=KIND_VISIT_START, plan_ref="p", occurred_at_ms=0, node_id="a")
    )
    obs.observe(GraphObservation(kind=KIND_VISIT_END, plan_ref="p", occurred_at_ms=0, node_id="a"))
    obs.observe(
        GraphObservation(kind=KIND_EDGE, plan_ref="p", occurred_at_ms=0, from_node="a", to_node="b")
    )
    obs.observe(GraphObservation(kind=KIND_SUBGRAPH_ENTER, plan_ref="p", occurred_at_ms=0))
    obs.observe(
        GraphObservation(kind=KIND_SUBGRAPH_EXIT, plan_ref="p", occurred_at_ms=0, outcome="success")
    )
    assert emitted == [
        "custom.visit",
        "custom.end",
        "custom.edge",
        "custom.sub.in",
        "custom.sub.out",
    ]


def test_spine_observer_drops_unknown_kind_without_raising() -> None:
    emitted: list[str] = []
    obs = SpineGraphObserver(emit=lambda ep, _p: emitted.append(ep))
    obs.observe(GraphObservation(kind="bogus_kind", plan_ref="p", occurred_at_ms=0))
    assert emitted == []


def test_spine_observer_contains_emit_failure() -> None:
    def broken(ep, payload):
        raise RuntimeError("sink down")

    obs = SpineGraphObserver(emit=broken)
    obs.observe(
        GraphObservation(kind=KIND_VISIT_START, plan_ref="p", occurred_at_ms=0, node_id="a")
    )


@pytest.mark.asyncio
async def test_subgraph_strategy_emits_enter_exit(monkeypatch) -> None:
    from lca.framework.graph.strategies.subgraph_strategy import SubgraphStrategy

    rec = RecordingObserver()
    monkeypatch.setattr(
        "lca.framework.graph.strategies.subgraph_strategy._load_subgraph_plan",
        lambda ref, entry: _make_plan(),
    )

    async def runner(sub_plan, outer_state, depth, outer_ports, outer_mirror=None):
        return {"decision": "ok"}

    strategy = SubgraphStrategy(recursive_runner=runner, observer=rec)
    ctx = _subgraph_context()
    out = await strategy.execute(ctx, NodeInput(port_values={}))
    assert out.port_values == {"decision": "ok"}
    kinds = [e.kind for e in rec.events]
    assert kinds[0] == KIND_SUBGRAPH_ENTER
    assert kinds[-1] == KIND_SUBGRAPH_EXIT
    exit_ev = rec.events[-1]
    assert exit_ev.outcome == "success"
    assert exit_ev.error == ""


@pytest.mark.asyncio
async def test_subgraph_strategy_emits_failure_exit(monkeypatch) -> None:
    from lca.framework.graph.strategies.subgraph_strategy import SubgraphStrategy

    rec = RecordingObserver()
    monkeypatch.setattr(
        "lca.framework.graph.strategies.subgraph_strategy._load_subgraph_plan",
        lambda ref, entry: _make_plan(),
    )

    async def runner(sub_plan, outer_state, depth, outer_ports, outer_mirror=None):
        raise RuntimeError("subgraph boom")

    strategy = SubgraphStrategy(recursive_runner=runner, observer=rec)
    ctx = _subgraph_context()
    with pytest.raises(RuntimeError, match="subgraph boom"):
        await strategy.execute(ctx, NodeInput(port_values={}))
    exits = rec.by_kind(KIND_SUBGRAPH_EXIT)
    assert len(exits) == 1
    assert exits[0].outcome == "failure"
    assert "subgraph boom" in exits[0].error


def _subgraph_context() -> StrategyContext:
    from lca.contracts.protocols.graph.plan import SubgraphReference

    return StrategyContext(
        plan_ref="outer",
        node_id="think.subgraph.reason",
        binding_kind=BindingKind.SUBGRAPH,
        node_config={},
        subgraph_ref=SubgraphReference(
            plan_ref="bundles/think-subgraph.yaml",
            entry_node="think.subgraph.shortcut",
            binding_edge="e_reason_inner",
        ),
        chain=(),
    )
