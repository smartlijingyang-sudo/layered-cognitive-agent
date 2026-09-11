"""Tests for the PR-7 production cutover adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.contracts.protocols.graph.strategy import NodeStrategy, StrategyContext
from lca.contracts.protocols.graph.node_io import NodeInput, NodeOutput
from lca.framework.graph import PlanInterpreterAdapter, StrategyRegistry


@dataclass(frozen=True, slots=True)
class _StubExec(NodeStrategy):
    """Strategy that emits a fixed response payload."""

    kind: BindingKind
    schema: NodeIOSchema
    payload: dict[str, Any]

    async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
        return NodeOutput(port_values=dict(self.payload), producer_node=context.node_id)


def _executable_for(plan: Plan) -> object:
    @dataclass
    class _PlanWrapper:
        phase_graph: Plan

    @dataclass
    class _Exec:
        plan: _PlanWrapper

    return _Exec(plan=_PlanWrapper(phase_graph=plan))


class TestPlanInterpreterAdapter:
    async def test_run_delegates_to_plan_interpreter(self) -> None:
        registry = StrategyRegistry()
        registry.register(_StubExec(kind=BindingKind.TRANSFORM, schema=NodeIOSchema(), payload={"response": "ok"}))
        adapter = PlanInterpreterAdapter(registry=registry)
        plan = Plan(
            id="p",
            nodes=(
                PlanNode(id="a", binding=BindingKind.TRANSFORM, entry=True),
            ),
            edges=(),
        )
        exec_obj = _executable_for(plan)
        result = await adapter.run(executable=exec_obj, state=None)
        assert result.terminal_node == "a"
        assert result.output["response"] == "ok"

    async def test_resume_falls_back_to_run(self) -> None:
        registry = StrategyRegistry()
        registry.register(_StubExec(kind=BindingKind.TRANSFORM, schema=NodeIOSchema(), payload={"response": "r"}))
        adapter = PlanInterpreterAdapter(registry=registry)
        plan = Plan(id="p", nodes=(PlanNode(id="a", binding=BindingKind.TRANSFORM, entry=True),), edges=())
        exec_obj = _executable_for(plan)
        result = await adapter.resume(
            executable=exec_obj,
            state=None,
            cursor=None,
        )
        assert result.terminal_node == "a"

    async def test_factory_returns_adapter(self) -> None:
        from lca.framework.declarative.plugins.interpreter_factory import (
            DefaultDeclarativeInterpreterFactory,
        )

        factory = DefaultDeclarativeInterpreterFactory()
        interpreter = factory.create(
            journal=None,
            effect_gateway=None,
            reducer=None,
            phase_observer=None,
            lifecycle_publisher=None,
        )
        assert isinstance(interpreter, PlanInterpreterAdapter)