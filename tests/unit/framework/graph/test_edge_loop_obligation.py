"""Regression: EdgeLoopObligation is enforced at runtime.

Without runtime enforcement, an act→think re-ask edge with
``loop.maxIterations=N`` is a no-op — the kernel keeps picking the
edge on every cycle. This pins that ``select_edge`` honours the
obligation once ``edge_counts[(source, target)] >= maxIterations``
and that the interpreter fail-louds via
:class:`LoopObligationExceededError` when no fallback matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import LoopObligationExceededError
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
    PortSpec,
)
from lca.contracts.protocols.graph.plan import (
    EdgeLoopObligation,
    Plan,
    PlanEdge,
    PlanNode,
)
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.contracts.protocols.graph.strategy import (
    NodeStrategy,
    StrategyContext,
)
from lca.framework.graph import (
    PlanInterpreter,
    PortRegistry,
    StrategyRegistry,
)
from lca.framework.graph.traversal import select_edge


def _plan_reask_only() -> Plan:
    """shortcut → reader → shortcut (re-ask). shortcut carries an
    empty-output contract; reader's only outgoing edge is bounded.
    """
    return Plan(
        id="reask-test",
        nodes=(
            PlanNode(
                id="shortcut",
                binding=BindingKind.TRANSFORM,
                entry=True,
                io_schema=NodeIOSchema(
                    outputs=(PortSpec(name=PortName("decision"), required=False),)
                ),
            ),
            PlanNode(
                id="reader",
                binding=BindingKind.NODE_EXECUTOR,
                io_schema=NodeIOSchema(
                    inputs=(PortSpec(name=PortName("decision"), required=True),)
                ),
            ),
        ),
        edges=(
            PlanEdge(source="shortcut", target="reader"),
            PlanEdge(
                source="reader",
                target="shortcut",
                loop=EdgeLoopObligation(max_iterations=2, budget="run.steps"),
            ),
        ),
    )


def _shortcut_emitting_then_empty() -> NodeStrategy:
    counter = {"n": 0}
    schema = NodeIOSchema(outputs=(PortSpec(name=PortName("decision"), required=False),))

    @dataclass(frozen=True, slots=True)
    class _Shortcut(NodeStrategy):
        kind: BindingKind = BindingKind.TRANSFORM
        schema: NodeIOSchema = field(default_factory=lambda: schema)

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            counter["n"] += 1
            # First visit emits; later visits return empty. Without
            # Fix 1's clear-on-empty contract the reader would see the
            # stale value forever; with Fix 1 the empty visit clears
            # it and the re-ask naturally dies — but the loop
            # obligation makes the death loud.
            if counter["n"] == 1:
                return NodeOutput(
                    port_values={"decision": "first-use-tool"},
                    producer_node=context.node_id,
                )
            return NodeOutput(port_values={}, producer_node=context.node_id)

    return _Shortcut()


def _terminating_reader() -> NodeStrategy:
    schema = NodeIOSchema(inputs=(PortSpec(name=PortName("decision"), required=True),))

    @dataclass(frozen=True, slots=True)
    class _Reader(NodeStrategy):
        kind: BindingKind = BindingKind.NODE_EXECUTOR
        schema: NodeIOSchema = field(default_factory=lambda: schema)

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            # Reader consumes decision; emits nothing — the only path
            # forward is the bounded re-ask edge back to shortcut.
            return NodeOutput(port_values={}, producer_node=context.node_id)

    return _Reader()


async def test_edge_loop_obligation_exceeded_raises() -> None:
    """Bounded edge + no fallback → LoopObligationExceededError.

    Simulates the 2026-09-16 act→think re-ask loop class:
    shortcut emits a stale Decision once, reader forwards it back,
    the bound is hit on the third take, and the kernel fail-louds.
    """
    registry = StrategyRegistry()
    registry.register(_shortcut_emitting_then_empty())
    registry.register(_terminating_reader())

    interp = PlanInterpreter(registry=registry)
    with pytest.raises(LoopObligationExceededError) as exc_info:
        await interp.run(_plan_reask_only(), port_registry=PortRegistry())

    err = exc_info.value
    assert err.source == "reader"
    assert err.target == "shortcut"
    assert err.max_iterations == 2
    assert err.taken is not None and err.taken >= 2
    assert "loop.maxIterations" in str(err)


def test_select_edge_skips_bounded_edge_when_quota_hit() -> None:
    """Pure ``select_edge`` smoke test: once the obligation is met,
    the edge is skipped; a fallback wins.
    """
    edge = PlanEdge(
        source="a",
        target="b",
        when=Predicate(
            kind="eq",
            port=PortRef(name="routing", field="action_type"),
            value="x",
        ),
        loop=EdgeLoopObligation(max_iterations=1, budget="run.steps"),
    )
    fallback = PlanEdge(source="a", target="c")
    reg = PortRegistry()
    reg.merge_output({"routing": "x"})

    factory = lambda src: _reader_for(src, reg)  # noqa: E731

    chosen = select_edge(
        edges=(edge, fallback),
        current_id="a",
        reader_factory=factory,
        edge_counts={("a", "b"): 1},  # already taken
    )
    assert chosen is not None
    assert chosen.target == "c"


def _reader_for(source: str, reg: PortRegistry):
    from lca.framework.graph.port_reader import PortReader

    return PortReader(source_node=source, registry=reg)
