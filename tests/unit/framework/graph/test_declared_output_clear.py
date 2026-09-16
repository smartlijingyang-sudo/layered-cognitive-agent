"""Regression: PlanInterpreter clears declared outputs each visit.

Background
----------

``PortRegistry.merge_output`` is last-write-wins per ADR-0217 §3.3.3
iron rule 5. But it only writes the keys the strategy actually
returned — an empty ``NodeOutput(port_values={})`` is a no-op. If a
node declares ``decision`` as an output and visits twice, the second
visit's empty output must clear ``decision`` from the registry,
otherwise the next consumer reads the previous visit's stale value.

Real-world failure mode (2026-09-16 stall postmortem):

- ``think.shortcut`` declares ``outputs=[decision]`` and returns an
  empty port_values when ``SupportsShortcut`` is not wired (the
  web-standard production path).
- ``think.route.decide`` reads ``decision`` from the registry to
  decide between short-circuit and miss-path. Because the empty
  NodeOutput didn't clear the registry, the stale ``use_tool``
  Decision from the previous think turn was read back as if the
  current shortcut had produced it.
- Result: ``act → think → act → think`` infinite re-ask loop, ~880
  empty think turns while LLM was never re-invoked.

This file pins the contract: declared outputs are always written per
visit; an absent value in the strategy's ``port_values`` means
``None`` (cleared), not "keep the previous iteration's value".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
    PortSpec,
)
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.ports import PortName
from lca.contracts.protocols.graph.strategy import (
    NodeStrategy,
    StrategyContext,
)
from lca.framework.graph import (
    PlanInterpreter,
    PortRegistry,
    StrategyRegistry,
)


def _plan_shortcut_then_reader() -> Plan:
    """shortcut → reader.

    shortcut declares ``decision`` as output; reader declares
    ``decision`` as input and ``decision_seen`` as output. One
    visit of each per ``PlanInterpreter.run`` call.
    """
    return Plan(
        id="clear-test",
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
                    inputs=(PortSpec(name=PortName("decision"), required=True),),
                    outputs=(PortSpec(name=PortName("decision_seen"), required=False),),
                ),
            ),
        ),
        edges=(PlanEdge(source="shortcut", target="reader"),),
    )


def _shortcut_strategy(*, emit_first: dict[str, Any] | None) -> NodeStrategy:
    """Emit ``emit_first`` on visit 1, empty dict thereafter.

    StrategyRegistry keys by BindingKind, so a closure-captured
    counter is the cleanest way to vary per-visit behaviour.
    """
    counter = {"n": 0}
    schema = NodeIOSchema(outputs=(PortSpec(name=PortName("decision"), required=False),))

    @dataclass(frozen=True, slots=True)
    class _Shortcut(NodeStrategy):
        kind: BindingKind = BindingKind.TRANSFORM
        schema: NodeIOSchema = field(default_factory=lambda: schema)

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            counter["n"] += 1
            if counter["n"] == 1 and emit_first is not None:
                return NodeOutput(
                    port_values=dict(emit_first),
                    producer_node=context.node_id,
                )
            return NodeOutput(port_values={}, producer_node=context.node_id)

    return _Shortcut()


def _reader_strategy(seen: list[Any]) -> NodeStrategy:
    schema = NodeIOSchema(
        inputs=(PortSpec(name=PortName("decision"), required=True),),
        outputs=(PortSpec(name=PortName("decision_seen"), required=False),),
    )

    @dataclass(frozen=True, slots=True)
    class _Reader(NodeStrategy):
        kind: BindingKind = BindingKind.NODE_EXECUTOR
        schema: NodeIOSchema = field(default_factory=lambda: schema)

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            value = input.port_values.get("decision")
            seen.append(value)
            return NodeOutput(
                port_values={"decision_seen": value},
                producer_node=context.node_id,
            )

    return _Reader()


async def test_declared_output_clears_on_empty_node_output() -> None:
    """Round 1 emits decision; round 2 empty output clears it.

    Two sequential ``PlanInterpreter.run`` calls share one
    :class:`PortRegistry` — this is the production shape of the
    ``act → think`` re-ask (the outer plan re-enters think.subgraph
    with the kernel-wide registry). Without the contract honored,
    round 2's reader would see ``"first-use-tool"`` (stale from
    round 1) instead of ``None``.
    """
    seen: list[Any] = []
    registry = StrategyRegistry()
    registry.register(_shortcut_strategy(emit_first={"decision": "first-use-tool"}))
    registry.register(_reader_strategy(seen))

    ports = PortRegistry()
    interp = PlanInterpreter(registry=registry)
    plan = _plan_shortcut_then_reader()
    await interp.run(plan, port_registry=ports)
    await interp.run(plan, port_registry=ports)

    assert seen == ["first-use-tool", None], (
        "Declared output port must be cleared each visit when the "
        "strategy returns an empty port_values; otherwise stale "
        "values from previous iterations leak across re-asks. "
        f"got {seen!r}"
    )


async def test_declared_output_overwrites_with_fresh_value() -> None:
    """Sanity: strategies that DO emit a value keep producing fresh values.

    Guards against an over-eager "always write None" fix.
    """
    counter = {"n": 0}
    schema = NodeIOSchema(outputs=(PortSpec(name=PortName("decision"), required=False),))

    @dataclass(frozen=True, slots=True)
    class _Emitter(NodeStrategy):
        kind: BindingKind = BindingKind.TRANSFORM
        schema: NodeIOSchema = field(default_factory=lambda: schema)

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            counter["n"] += 1
            return NodeOutput(
                port_values={"decision": f"visit-{counter['n']}"},
                producer_node=context.node_id,
            )

    seen: list[Any] = []
    registry = StrategyRegistry()
    registry.register(_Emitter())
    registry.register(_reader_strategy(seen))

    ports = PortRegistry()
    interp = PlanInterpreter(registry=registry)
    plan = _plan_shortcut_then_reader()
    await interp.run(plan, port_registry=ports)
    await interp.run(plan, port_registry=ports)

    assert ports.snapshot()["decision"] == "visit-2"
    assert seen == ["visit-1", "visit-2"]


async def test_undeclared_output_is_silently_merged() -> None:
    """Pin current behaviour: a strategy returning a port NOT in its
    declared outputs is silently accepted by the interpreter (the
    D4 ``project_outputs`` validator is not wired into the v2 kernel
    loop). The clear-loop must not change this behaviour.
    """
    schema = NodeIOSchema()

    @dataclass(frozen=True, slots=True)
    class _Producer(NodeStrategy):
        kind: BindingKind = BindingKind.TRANSFORM
        schema: NodeIOSchema = field(default_factory=lambda: schema)

        async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
            return NodeOutput(port_values={"rogue": 1}, producer_node=context.node_id)

    registry = StrategyRegistry()
    registry.register(_Producer())

    plan = Plan(
        id="rogue",
        nodes=(
            PlanNode(id="p", binding=BindingKind.TRANSFORM, entry=True),
            PlanNode(id="q", binding=BindingKind.TRANSFORM),
        ),
        edges=(PlanEdge(source="p", target="q"),),
    )

    ports = PortRegistry()
    interp = PlanInterpreter(registry=registry)
    await interp.run(plan, port_registry=ports)
    assert ports.snapshot().get("rogue") == 1
