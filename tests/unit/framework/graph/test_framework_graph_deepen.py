"""Characterization tests for framework/graph deepen (C2–C3).

C1 lift interface covered by tests/framework/graph/test_lift_interface.py.
No intended outer-loop behavior change.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeInput, NodeIOSchema, NodeOutput, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanNode, SubgraphReference
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.framework.graph.adapter import PlanInterpreterAdapter, _enter_subgraph, _exit_subgraph
from lca.framework.graph.host_wiring import (
    build_registry,
    enter_subgraph,
    exit_subgraph,
)
from lca.framework.graph.observation import NullGraphObserver
from lca.framework.graph.strategies.subgraph_run import (
    DefaultSubgraphRun,
    SubgraphRun,
    translate_inputs,
    translate_outputs,
)
from lca.framework.graph.strategies.subgraph_strategy import SubgraphStrategy
from lca.framework.graph.strategy_registry import StrategyRegistry, default_strategy_registry


class TestAdapterHostWiringSplit:
    def test_adapter_reexports_depth_helpers(self) -> None:
        depth, token = _enter_subgraph()
        assert depth == 0
        _exit_subgraph(token)
        d2, t2 = enter_subgraph()
        assert d2 == 0
        exit_subgraph(t2)

    def test_build_registry_wires_subgraph_runner(self) -> None:
        async def runner(plan, state, depth, ports=None, mirror=None):
            return {"x": 1}

        reg = build_registry(
            runner,
            lambda: 0,
            lambda *, binding, node_id, region: None,
            lambda state: state,
            NullGraphObserver(),
            lambda: 0,
            default_strategy_registry(),
        )
        strat = reg.resolve(BindingKind.SUBGRAPH)
        assert isinstance(strat, SubgraphStrategy)
        assert strat.recursive_runner is runner

    async def test_adapter_run_still_delegates(self) -> None:
        @dataclass(frozen=True, slots=True)
        class _Stub:
            kind: BindingKind
            schema: NodeIOSchema

            async def execute(self, context, input):
                return NodeOutput(port_values={"ok": True}, producer_node=context.node_id)

        registry = StrategyRegistry()
        registry.register(_Stub(kind=BindingKind.TRANSFORM, schema=NodeIOSchema()))
        adapter = PlanInterpreterAdapter(registry=registry)
        plan = Plan(
            id="p",
            nodes=(PlanNode(id="a", binding=BindingKind.TRANSFORM, entry=True),),
            edges=(),
        )

        @dataclass
        class _Wrap:
            phase_graph: Plan

        @dataclass
        class _Exec:
            plan: _Wrap

        result = await adapter.run(executable=_Exec(plan=_Wrap(phase_graph=plan)), state=None)
        assert result.terminal_node == "a"
        assert result.output["ok"] is True


class TestSubgraphRunDeepen:
    def test_translate_inputs_name_based(self) -> None:
        """ADR-0241 §1 — name-based projection at the subgraph seam.

        Outer ``observation`` matches inner declared ``observation`` by
        name; the old positional swap that renamed ``act_outcome`` to
        ``observation`` is no longer supported (it conflated two
        distinct ports and was the root cause of the slim-composer
        regression).
        """
        context = StrategyContext(
            plan_ref="outer",
            node_id="n",
            binding_kind=BindingKind.SUBGRAPH,
            node_config={},
            subgraph_ref=SubgraphReference(
                plan_ref="bundles/x.yaml", entry_node="entry", binding_edge="next"
            ),
            chain=(),
            inner_io_schema=NodeIOSchema(inputs=(PortSpec(name="observation"),)),
        )
        inp = NodeInput(port_values={"observation": {"v": 1}}, consumer_node="n")
        assert translate_inputs(context, inp) == {"observation": {"v": 1}}

    def test_translate_inputs_drops_outer_port_not_named_in_inner(self) -> None:
        """Outer port whose name is not in inner declared inputs is dropped.

        ADR-0241 §1: information leakage across the seam is forbidden.
        The outer port still reaches the inner ``PortRegistry`` via
        ``DefaultSubgraphRun`` seeding (separate code path), but the
        translator itself returns only the declared-named subset.
        """
        context = StrategyContext(
            plan_ref="outer",
            node_id="n",
            binding_kind=BindingKind.SUBGRAPH,
            node_config={},
            subgraph_ref=SubgraphReference(
                plan_ref="bundles/x.yaml", entry_node="entry", binding_edge="next"
            ),
            chain=(),
            inner_io_schema=NodeIOSchema(inputs=(PortSpec(name="observation"),)),
        )
        inp = NodeInput(port_values={"act_outcome": {"v": 1}}, consumer_node="n")
        # act_outcome is not in inner declared → dropped at translator.
        assert translate_inputs(context, inp) == {}

    def test_translate_outputs_positional(self) -> None:
        context = StrategyContext(
            plan_ref="outer",
            node_id="n",
            binding_kind=BindingKind.SUBGRAPH,
            node_config={"declared_outputs": ["act_outcome"]},
            subgraph_ref=None,
            chain=(),
            inner_io_schema=NodeIOSchema(outputs=(PortSpec(name="receipt"),)),
        )
        assert translate_outputs(context, {"receipt": {"ok": True}}) == {
            "act_outcome": {"ok": True}
        }

    async def test_default_subgraph_run_protocol(self) -> None:
        async def runner(plan, state, depth, ports=None, mirror=None):
            return {"receipt": 7}

        run: SubgraphRun = DefaultSubgraphRun(recursive_runner=runner, max_depth=4)
        import lca.framework.graph.strategies.subgraph_run as mod

        fake_plan = Plan(
            id="inner",
            nodes=(PlanNode(id="entry", binding=BindingKind.TRANSFORM, entry=True),),
            edges=(),
        )
        orig = mod.load_subgraph_plan
        mod.load_subgraph_plan = lambda plan_ref, entry_node: fake_plan
        try:
            context = StrategyContext(
                plan_ref="outer",
                node_id="sub",
                binding_kind=BindingKind.SUBGRAPH,
                node_config={"declared_outputs": ["act_outcome"]},
                subgraph_ref=SubgraphReference(
                    plan_ref="bundles/fake.yaml", entry_node="entry", binding_edge="next"
                ),
                chain=(),
                inner_io_schema=NodeIOSchema(outputs=(PortSpec(name="receipt"),)),
            )
            result = await run.run(context, NodeInput(port_values={}, consumer_node="sub"))
            assert result.port_values == {"act_outcome": 7}
        finally:
            mod.load_subgraph_plan = orig
