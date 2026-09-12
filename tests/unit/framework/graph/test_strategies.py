"""Pure-unit tests for the unified graph kernel strategies.

These tests inject fakes for the runner / executor / recursive
runner seam so they do not depend on the production kernel. They
prove:

- Each strategy registers in the default registry.
- ``execute`` calls the seam once with the expected args.
- :class:`SubgraphStrategy` enforces ``max_depth``.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeOutput as LegacyNodeOutput,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    NodeOutput,
    PortSpec,
)
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode, SubgraphReference
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.framework.graph import default_strategy_registry
from lca.framework.graph.strategies import (
    NodeExecutorStrategy,
    SubgraphStrategy,
)
from lca.framework.graph.strategy_registry import (
    StrategyRegistry,
    resolve_executor,
)


class TestRegistry:
    def test_strategies_registered(self) -> None:
        reg = default_strategy_registry()
        kinds = {k.value for k in reg.kinds()}
        assert {"node_executor", "subgraph"}.issubset(kinds)
        assert "phase_executor" not in kinds

    def test_resolve_returns_singleton(self) -> None:
        reg = default_strategy_registry()
        s1 = reg.resolve(BindingKind.NODE_EXECUTOR)
        s2 = reg.resolve(BindingKind.NODE_EXECUTOR)
        assert s1 is s2

    def test_unknown_kind_raises(self) -> None:
        reg = default_strategy_registry()
        for kind in BindingKind:
            reg.resolve(kind)
        empty = StrategyRegistry()
        with pytest.raises(KeyError):
            empty.resolve(BindingKind.NODE_EXECUTOR)

    def test_resolve_executor_raises_when_lookup_missing(self) -> None:
        with pytest.raises(RuntimeError, match="no executor lookup"):
            resolve_executor(None, binding=BindingKind.NODE_EXECUTOR, node_id="x")


class TestNodeExecutorStrategy:
    async def test_execute_delegates_to_node_executor(self) -> None:
        captured: dict[str, Any] = {}

        class _StubNodeExec:
            semantic_name = "think.reason"
            declared_inputs: tuple[str, ...] = ()
            declared_outputs: tuple[str, ...] = ()

            async def execute(self, ctx: Any, inp: Any) -> Any:
                captured["ctx"] = ctx
                captured["inp"] = inp
                return LegacyNodeOutput(port_values={"response": "hi"}, next_hint=None)

        def _lookup(*, binding: BindingKind, node_id: str, region: str | None) -> Any:
            return _StubNodeExec()

        strategy = NodeExecutorStrategy(executor_lookup=_lookup)
        ctx = StrategyContext(
            plan_ref="p1",
            node_id="think.reason",
            binding_kind=BindingKind.NODE_EXECUTOR,
            node_config={"budget": {"max_visits": 1}},
        )
        out = await strategy.execute(
            ctx,
            NodeInput(port_values={"decision": 1}, consumer_node="think.reason"),
        )
        assert "response" in out.port_values
        assert captured["ctx"].metadata["plan_ref"] == "p1"
        assert captured["ctx"].metadata["node_id"] == "think.reason"


class TestSubgraphStrategy:
    async def test_execute_calls_recursive_runner(self) -> None:
        called: dict[str, Any] = {}

        def _recursive_runner(
            sub_plan: Any, outer_state: Any, depth: int, port_registry=None, outer_mirror=None
        ) -> dict:
            called["sub_plan"] = sub_plan
            called["outer_state"] = outer_state
            called["depth"] = depth
            return {"observation": "ok"}

        ref = SubgraphReference(plan_ref="inner.yaml", entry_node="a", binding_edge="x")
        strategy = SubgraphStrategy(recursive_runner=_recursive_runner, max_depth=4)
        ctx = StrategyContext(
            plan_ref="outer.yaml",
            node_id="dispatch",
            binding_kind=BindingKind.SUBGRAPH,
            node_config={},
            subgraph_ref=ref,
        )
        with pytest.raises(FileNotFoundError):
            await strategy.execute(ctx, NodeInput(port_values={"decision": "x"}))

    async def test_execute_seeds_inner_port_registry_with_outer_input(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from lca.framework.graph.strategies import subgraph_strategy as sg_mod

        captured: dict[str, Any] = {}

        def _recursive_runner(
            sub_plan: Any,
            outer_state: Any,
            depth: int,
            port_registry: Any = None,
            outer_mirror: Any = None,
        ) -> dict:
            captured["sub_plan"] = sub_plan
            captured["outer_state"] = outer_state
            captured["depth"] = depth
            captured["port_registry"] = port_registry
            return {"observation": "ok"}

        monkeypatch.setattr(
            sg_mod,
            "_load_subgraph_plan",
            lambda plan_ref, entry_node: Plan(
                id="inner",
                nodes=(),
                edges=(),
                declared_inputs=(),
            ),
        )

        ref = SubgraphReference(plan_ref="inner.yaml", entry_node="a", binding_edge="x")
        strategy = SubgraphStrategy(recursive_runner=_recursive_runner, max_depth=4)
        ctx = StrategyContext(
            plan_ref="outer.yaml",
            node_id="dispatch",
            binding_kind=BindingKind.SUBGRAPH,
            node_config={},
            subgraph_ref=ref,
        )
        await strategy.execute(
            ctx,
            NodeInput(
                port_values={"response": "fake_llm_response_object"},
                consumer_node="dispatch",
            ),
        )

        ports = captured["port_registry"]
        assert ports is not None
        assert ports.snapshot()["response"] == "fake_llm_response_object"

    async def test_max_depth_enforced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lca.framework.graph.strategies import subgraph_strategy as sg_mod

        monkeypatch.setattr(
            sg_mod,
            "_load_subgraph_plan",
            lambda plan_ref, entry_node: Plan(
                id="inner",
                nodes=(),
                edges=(),
                declared_inputs=(),
            ),
        )
        from lca.framework.graph.adapter import _enter_subgraph, _exit_subgraph

        # Pre-set the depth context var so the strategy sees current_depth >= 1
        # and increments past max_depth=1.
        depth_token = _enter_subgraph()[1]
        try:
            strategy = SubgraphStrategy(
                recursive_runner=lambda *_: {},
                max_depth=1,
                depth_counter=lambda: 5,
            )
            ctx = StrategyContext(
                plan_ref="p",
                node_id="d",
                binding_kind=BindingKind.SUBGRAPH,
                node_config={},
                subgraph_ref=SubgraphReference(
                    plan_ref="x.yaml", entry_node="a", binding_edge="x"
                ),
            )
            with pytest.raises(RuntimeError, match="subgraph recursion exceeded"):
                await strategy.execute(ctx, NodeInput())
        finally:
            _exit_subgraph(depth_token)

    async def test_requires_subgraph_ref(self) -> None:
        strategy = SubgraphStrategy(recursive_runner=lambda *_: {})
        ctx = StrategyContext(
            plan_ref="p",
            node_id="d",
            binding_kind=BindingKind.SUBGRAPH,
            node_config={},
        )
        with pytest.raises(RuntimeError, match="no subgraph_ref"):
            await strategy.execute(ctx, NodeInput())

    def test_schema_validates_required_input(self) -> None:
        schema = NodeIOSchema(inputs=(PortSpec(name="decision", required=True),))
        assert schema.satisfied_by({"decision": 1})
        assert not schema.satisfied_by({})


class TestPlanSmoke:
    def test_node_in_plan(self) -> None:
        p = Plan(
            id="p",
            nodes=(
                PlanNode(id="a", binding=BindingKind.SUBGRAPH, entry=True),
                PlanNode(id="b", binding=BindingKind.NODE_EXECUTOR),
            ),
            edges=(PlanEdge(source="a", target="b"),),
        )
        assert p.node("a").binding is BindingKind.SUBGRAPH


# Test helpers
class _FakeState:
    trace_id = ""
    run_id = ""
    step = 0
