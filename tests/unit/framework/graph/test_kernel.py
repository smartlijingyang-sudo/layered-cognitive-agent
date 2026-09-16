"""Tests for the PR-4 kernel components.

Covers :class:`PortRegistry`, :class:`PlanTraversal`, :class:`VisitRecorder`,
the lifter functions, and :class:`PlanInterpreter` driven by stub
strategies registered for the test plan.

These tests prove the kernel's invariants directly:

- ``terminated()`` is True only after an ``advance(edge=None)``.
- :meth:`PlanInterpreter.run` walks the plan via edge selection
  (per-node ``max_visits`` was removed in ADR-0225).
- The recorder collects one :class:`VisitRecord` per visit.
- The lifter accepts both v2 graph spec dicts and legacy
  :class:`CognitivePhaseGraphPlan`-shaped objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
from lca.contracts.protocols.graph.visit import VisitRecord
from lca.framework.graph import (
    PlanInterpreter,
    PlanTraversal,
    PortRegistry,
    StrategyRegistry,
    VisitRecorder,
    lift_executable_plan,
    lift_graph_spec,
)


@dataclass(frozen=True, slots=True)
class _StubStrategy(NodeStrategy):
    """Test strategy that emits a fixed port_values mapping."""

    kind: BindingKind
    schema: NodeIOSchema
    emit: dict[PortName, Any]
    next_target: str | None = None

    async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
        return NodeOutput(
            port_values=dict(self.emit),
            producer_node=context.node_id,
        )


class TestPortRegistry:
    def test_merge_output_overrides_outer_input_in_iteration(self) -> None:
        """ADR-0217 §3.3.3 iron rule 5: merge_output last-write-wins.

        ``set_outer_input`` (iron rule 1) only seeds empty slots — once
        an inner node writes via ``merge_output`` the registry carries
        that value. Subsequent ``merge_output`` calls overwrite the
        same port (last-write-wins) so outer-loop iterations see the
        current iteration's typed ports instead of stale step-1 DTOs.
        """
        reg = PortRegistry()
        reg.set_outer_input({"decision": "outer"})
        reg.merge_output({"decision": "inner"})
        assert reg.snapshot()["decision"] == "inner"

    def test_build_input_projects_required_ports(self) -> None:
        reg = PortRegistry()
        reg.set_outer_input({"decision": "d", "observation": "o"})
        node_input = reg.build_input(("decision", "response"))
        assert node_input.port_values["decision"] == "d"
        assert node_input.port_values["response"] is None

    def test_exit_subgraph_passthrough(self) -> None:
        reg = PortRegistry()
        reg.merge_output({"decision": "d"})
        out = reg.exit_subgraph(("decision", "response"))
        assert out == {"decision": "d"}
        assert "response" not in out


class TestPlanTraversal:
    def test_entry_id_resolved_from_plan(self) -> None:
        plan = _make_plan(("a", "b"))
        trav = PlanTraversal(plan=plan)
        assert trav.current_id == "a"

    def test_visit_increments_count(self) -> None:
        """ADR-0225: ``visit`` still increments ``visit_counts`` (used
        by resume replays); it no longer flips ``terminal`` on a
        per-node ceiling."""
        plan = _make_plan(("a", "b"))
        trav = PlanTraversal(plan=plan)
        trav.visit(node_id="a")
        trav.visit(node_id="a")
        assert trav.visit_counts["a"] == 2
        assert trav.terminal is False

    def test_advance_with_edge(self) -> None:
        plan = _make_plan(("a", "b"))
        trav = PlanTraversal(plan=plan)
        edge = plan.edges[0]
        trav.advance(edge=edge, dispatch_kind="next")
        assert trav.current_id == "b"
        assert not trav.terminated()

    def test_advance_without_edge_terminates(self) -> None:
        plan = _make_plan(("a", "b"))
        trav = PlanTraversal(plan=plan)
        trav.advance(edge=None, dispatch_kind="terminal")
        assert trav.terminated()

    def test_fork_resets_cursor(self) -> None:
        plan = _make_plan(("a", "b"))
        trav = PlanTraversal(plan=plan)
        sub = trav.fork(entry="b")
        assert sub.current_id == "b"
        assert sub.plan is plan


class TestVisitRecorder:
    def test_records_and_query(self) -> None:
        rec = VisitRecorder()
        rec.record(_make_record("a"))
        rec.record(_make_record("b"))
        rec.record(_make_record("a"))
        assert len(rec.all()) == 3
        assert {r.node_id for r in rec.by_node("a")} == {"a"}
        assert rec.last().node_id == "a"


class TestLifter:
    def test_lift_graph_spec_minimal(self) -> None:
        spec = {
            "id": "p1",
            "entry": "a",
            "nodes": [
                {"id": "a", "binding": "node_executor", "entry": True},
                {"id": "b", "binding": "node_executor", "terminal": True},
            ],
            "edges": [{"from": "a", "to": "b", "when": "true"}],
        }
        plan = lift_graph_spec(spec)
        assert plan.id == "p1"
        assert len(plan.nodes) == 2
        assert plan.nodes[0].binding is BindingKind.NODE_EXECUTOR
        assert plan.edges[0].source == "a"
        assert plan.edges[0].target == "b"

    def test_lift_graph_spec_optional_inputs_outputs(self) -> None:
        spec = {
            "id": "p",
            "entry": "a",
            "nodes": [
                {
                    "id": "a",
                    "binding": "transform",
                    "entry": True,
                    "terminal": True,
                    "inputs": ["decision"],
                    "outputs": ["observation"],
                },
            ],
        }
        plan = lift_graph_spec(spec)
        assert plan.nodes[0].io_schema.required_inputs() == ("decision",)
        assert "observation" in plan.nodes[0].io_schema.output_names()

    def test_lift_graph_spec_rejects_unknown_binding(self) -> None:
        with pytest.raises(ValueError, match="binding must be"):
            lift_graph_spec({"id": "p", "nodes": [{"id": "a", "binding": 42}]})

    def test_lift_executable_plan(self) -> None:
        @dataclass
        class _Edge:
            source: str
            target: str
            when: str = "true"

        @dataclass
        class _Node:
            id: str
            binding: str | None
            sub_spec_ref: Any = None
            terminal: bool = False
            entry: bool = False

        @dataclass
        class _Graph:
            nodes: list[_Node]
            edges: list[_Edge]
            approval_resume_node: str | None = None

        @dataclass
        class _Plan:
            id: str
            phase_graph: _Graph

        plan_obj = _Plan(
            id="outer",
            phase_graph=_Graph(
                nodes=[
                    _Node(id="perceive", binding="node_executor", entry=True),
                    _Node(id="think", binding=None, sub_spec_ref="sub.yaml"),
                ],
                edges=[_Edge(source="perceive", target="think")],
            ),
        )

        @dataclass
        class _Exec:
            plan: Any

        lifted = lift_executable_plan(_Exec(plan=plan_obj))
        assert lifted.id == "outer"
        assert lifted.nodes[0].binding is BindingKind.NODE_EXECUTOR
        assert lifted.nodes[1].binding is BindingKind.SUBGRAPH

    @pytest.mark.xfail(
        reason="D5 validation catches real bug: terminal.commit edge references 'routing' port not in outputs. "
        "D4 bundle rewrite will fix this.",
        strict=True,
    )
    def test_lift_graph_spec_subgraph_ref_inherits_inner_entry_schema(self) -> None:
        """An outer node carrying ``sub_spec_ref`` must declare its
        io_schema from the inner entry node's ports so the kernel
        forwards the right outer registry values into the subgraph.

        Regression for the v2 driver bug where ``phase.main.outer``'s
        ``act.main`` had empty ``io_schema.inputs`` (the lifter read
        ``raw.get("inputs")`` instead of inheriting the inner entry's
        schema), so ``act.validate`` received ``decision=None`` even
        though ``think.main`` produced a USE_TOOL Decision.

        See run_d30a634f057b / run_6ad8ca880cef — every node-only
        ``declared_inputs/declared_outputs`` field on the outer v2
        yaml is ignored unless the lifter falls back to the inner
        entry's schema when ``sub_spec_ref`` is wired.
        """
        from pathlib import Path as _Path

        import yaml as _yaml

        repo_root = _Path(__file__).resolve().parents[4]
        outer_yaml = (repo_root / "bundles" / "outer" / "phase_main.yaml").read_text(encoding="utf-8")
        spec = _yaml.safe_load(outer_yaml)
        plan = lift_graph_spec(spec)

        nodes_by_id = {n.id: n for n in plan.nodes}
        act_main = nodes_by_id["act.main"]
        # Outer act.main carries a sub_spec_ref pointing at act.yaml.
        # Its inner entry is ``act.validate`` whose declared inputs
        # include ``decision`` (the port we need to forward from the
        # prior phase). The lifter must surface this so the kernel
        # calls ``build_input(["decision"], ...)`` and the subgraph
        # entry sees the Decision instance.
        assert act_main.subgraph_ref is not None
        assert act_main.subgraph_ref.entry_node == "act.validate"
        assert "decision" in act_main.io_schema.required_inputs()


class TestPlanInterpreter:
    async def test_run_visits_each_node_once(self) -> None:
        plan = _make_plan(("a", "b", "c"))
        registry = _registry_with_stubs(plan)
        interp = PlanInterpreter(registry=registry)
        result = await interp.run(plan)
        assert result.terminal_node == "c"
        assert len(result.visits) == 3

    async def test_run_terminates_when_no_outgoing_edge(self) -> None:
        plan = _make_plan(("a",))
        registry = _registry_with_stubs(plan)
        interp = PlanInterpreter(registry=registry)
        result = await interp.run(plan)
        assert result.terminal_node == "a"
        assert interp.recorder.last().dispatch.kind == "terminal"

    async def test_recorder_collects_visits(self) -> None:
        plan = _make_plan(("a", "b"))
        registry = _registry_with_stubs(plan)
        interp = PlanInterpreter(registry=registry)
        await interp.run(plan)
        assert {r.node_id for r in interp.recorder.all()} == {"a", "b"}

    async def test_visit_record_carries_inputs_outputs(self) -> None:
        plan = _make_plan(("a",))
        registry = _registry_with_stubs(
            plan,
            emits={"a": {"decision": "d-from-a"}},
        )
        interp = PlanInterpreter(registry=registry)
        await interp.run(plan)
        visit = interp.recorder.last()
        assert visit is not None
        assert visit.outputs["decision"] == "d-from-a"

    async def test_run_terminates_naturally_on_self_loop(self) -> None:
        """Regression: a self-looping plan terminates via ``terminal_predicate``,
        not via a per-node ``max_visits`` cap.

        ADR-0225: the kernel no longer trips a per-node ceiling; the
        interpreter exits the loop because the strategy's
        ``terminal_predicate`` matches after the second visit (when
        the strategy emits a ``done`` port).
        """
        from lca.contracts.protocols.graph.predicate import PortRef, Predicate

        term_pred = Predicate(kind="exists", port=PortRef(name="done"), value=True)
        plan = Plan(
            id="loop-plan",
            nodes=(
                PlanNode(
                    id="a",
                    binding=BindingKind.TRANSFORM,
                    entry=True,
                    io_schema=NodeIOSchema(terminal_predicate=term_pred),
                ),
            ),
            edges=(PlanEdge(source="a", target="a"),),
        )

        counter = {"n": 0}

        @dataclass(frozen=True, slots=True)
        class _Counting(NodeStrategy):
            kind: BindingKind = BindingKind.TRANSFORM
            schema: NodeIOSchema = field(
                default_factory=lambda: NodeIOSchema(terminal_predicate=term_pred)
            )

            async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
                counter["n"] += 1
                emit: dict[PortName, Any] = {"done": True} if counter["n"] >= 2 else {}
                return NodeOutput(port_values=emit, producer_node=context.node_id)

        registry = StrategyRegistry()
        registry.register(_Counting())
        interp = PlanInterpreter(registry=registry)
        result = await interp.run(plan)
        assert counter["n"] >= 2, "self-loop should have run at least twice"
        assert result.terminal_node == "a"
        # None of the recorded visits should mention ``budget_exceeded``:
        # the kernel never trips a per-node ceiling.
        assert all(
            visit.error is None or "budget_exceeded" not in str(visit.error).lower()
            for visit in result.visits
        )


def _make_plan(
    node_ids: tuple[str, ...],
) -> Plan:
    nodes: list[PlanNode] = []
    edges: list[PlanEdge] = []
    for idx, nid in enumerate(node_ids):
        nodes.append(
            PlanNode(
                id=nid,
                binding=BindingKind.TRANSFORM,
                entry=(idx == 0),
            )
        )
        if idx > 0:
            edges.append(PlanEdge(source=node_ids[idx - 1], target=nid))
    return Plan(id="test-plan", nodes=tuple(nodes), edges=tuple(edges))


def _registry_with_stubs(
    plan: Plan,
    *,
    emits: dict[str, dict[str, Any]] | None = None,
) -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(
        _StubStrategy(
            kind=BindingKind.TRANSFORM,
            schema=NodeIOSchema(),
            emit={
                ((emits or {}).get("a", {}).get("decision") and "decision") or "decision": (
                    (emits or {}).get("a", {}).get("decision") or "d"
                )
            },
            next_target="b",
        )
    )
    registry.register(
        _StubStrategy(
            kind=BindingKind.NODE_EXECUTOR,
            schema=NodeIOSchema(),
            emit={"decision": "p"},
        )
    )
    registry.register(
        _StubStrategy(
            kind=BindingKind.SUBGRAPH,
            schema=NodeIOSchema(),
            emit={"observation": "s"},
        )
    )
    return registry


def _make_record(node_id: str) -> VisitRecord:
    from lca.contracts.protocols.graph.visit import DispatchDecision

    return VisitRecord(
        plan_ref="p",
        node_id=node_id,
        binding_kind=BindingKind.TRANSFORM,
        dispatch=DispatchDecision(kind="next", next_node="next"),
    )


@dataclass(frozen=True, slots=True)
class _DecisionOnly(NodeStrategy):
    """Emits a single ``decision`` port; declares nothing else."""

    kind: BindingKind = BindingKind.TRANSFORM
    schema: NodeIOSchema = field(default_factory=NodeIOSchema)

    async def execute(self, context: StrategyContext, input: NodeInput) -> NodeOutput:
        return NodeOutput(port_values={"decision": "d"}, producer_node=context.node_id)


def _plan_with_terminal_predicate(pred: object) -> Plan:
    return Plan(
        id="tp-plan",
        nodes=(
            PlanNode(
                id="a",
                binding=BindingKind.TRANSFORM,
                entry=True,
                io_schema=NodeIOSchema(terminal_predicate=pred),  # type: ignore[arg-type]
            ),
            PlanNode(
                id="b",
                binding=BindingKind.TRANSFORM,
                io_schema=NodeIOSchema(),
            ),
        ),
        edges=(PlanEdge(source="a", target="b"),),
    )


class TestTerminalPredicateErrorClassification:
    """D4: "no data yet" is not the same as "the plan is malformed"."""

    async def test_unset_port_falls_through_to_edge_selection(self) -> None:
        from lca.contracts.protocols.graph.predicate import PortRef, Predicate

        pred = Predicate(kind="eq", port=PortRef(name="never_emitted"), value=1)
        registry = StrategyRegistry()
        registry.register(_DecisionOnly())
        interp = PlanInterpreter(registry=registry)

        result = await interp.run(_plan_with_terminal_predicate(pred))

        assert [v.node_id for v in result.visits] == ["a", "b"]
        assert result.terminal_node == "b"

    async def test_malformed_predicate_surfaces(self) -> None:
        from lca.contracts.protocols.graph.predicate import Predicate

        pred = Predicate(kind="eq", value=1)  # leaf without ``port``
        registry = StrategyRegistry()
        registry.register(_DecisionOnly())
        interp = PlanInterpreter(registry=registry)

        with pytest.raises(ValueError, match="requires 'port'"):
            await interp.run(_plan_with_terminal_predicate(pred))
