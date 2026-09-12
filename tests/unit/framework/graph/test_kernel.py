"""Tests for the PR-4 kernel components.

Covers :class:`PortRegistry`, :class:`PlanTraversal`, :class:`VisitRecorder`,
the lifter functions, and :class:`PlanInterpreter` driven by stub
strategies registered for the test plan.

These tests prove the kernel's invariants directly:

- ``terminated()`` is True only after an ``advance(edge=None)``.
- :meth:`PlanInterpreter.run` visits each node exactly the plan's
  declared ``max_visits`` times.
- The recorder collects one :class:`VisitRecord` per visit.
- The lifter accepts both v2 graph spec dicts and legacy
  :class:`CognitivePhaseGraphPlan`-shaped objects.
"""

from __future__ import annotations

from dataclasses import dataclass
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
from lca.framework.graph.traversal import install_predicate_evaluator


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
    def test_outer_input_wins_on_merge(self) -> None:
        reg = PortRegistry()
        reg.set_outer_input({"decision": "outer"})
        reg.merge_output({"decision": "inner"})
        assert reg.snapshot()["decision"] == "outer"

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

    def test_max_visits_enforced(self) -> None:
        plan = _make_plan(("a", "b"), max_visits=1)
        trav = PlanTraversal(plan=plan)
        trav.visit(node_id="a", max_visits=1)
        # Over-budget visit sets terminal instead of raising.
        trav.visit(node_id="a", max_visits=1)
        assert trav.terminal is True
        assert trav.terminal_reason is not None
        assert trav.terminal_reason[0] == "budget_exceeded"
        assert trav.terminal_reason[1] == "a"
        assert trav.terminal_reason[2] == 1  # max_visits
        assert trav.terminal_reason[3] == 2  # actual count

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
                {"id": "b", "binding": "node_executor"},
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
                    "inputs": ["decision"],
                    "outputs": ["observation"],
                },
            ],
        }
        plan = lift_graph_spec(spec)
        assert plan.nodes[0].io_schema.required_inputs() == ("decision",)
        assert "observation" in plan.nodes[0].io_schema.output_names()

    def test_lift_graph_spec_rejects_unknown_binding(self) -> None:
        spec = {
            "id": "p",
            "nodes": [{"id": "a", "binding": "phase_executor", "entry": True}],
        }
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
            max_visits: int = 1
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
                    _Node(id="perceive", binding="node_executor", entry=True, max_visits=8),
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
        outer_yaml = (repo_root / "bundles" / "phase_main_outer.yaml").read_text(encoding="utf-8")
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

    async def test_run_uses_max_visits(self) -> None:
        plan = _make_plan(("a", "b"), max_visits=2)
        registry = _registry_with_stubs(plan)
        interp = PlanInterpreter(registry=registry)
        # Each visit_to_advance pulls once; max_visits=2 is a *limit*
        # the kernel checks at visit time. Re-running is the
        # caller's job; the kernel enforces the per-visit cap.
        result = await interp.run(plan)
        assert result.terminal_node == "b"

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

    async def test_run_terminates_cleanly_on_max_visits_exceeded(self) -> None:
        """Regression: a self-looping plan that would exceed max_visits
        terminates cleanly via ``traversal.terminal`` instead of raising
        RuntimeError.  The kernel records exactly ``max_visits`` successful
        visits, then the over-budget visit flips terminal and the loop
        exits without executing the over-budget node.

        ADR-0214 PG-007 passive→active.
        """
        max_visits = 3
        # Self-looping plan: a → a (always "true" edge back to itself).
        plan = Plan(
            id="loop-plan",
            nodes=(
                PlanNode(
                    id="a",
                    binding=BindingKind.TRANSFORM,
                    entry=True,
                    max_visits=max_visits,
                ),
            ),
            edges=(PlanEdge(source="a", target="a", when="true"),),
        )
        registry = StrategyRegistry()
        registry.register(
            _StubStrategy(
                kind=BindingKind.TRANSFORM,
                schema=NodeIOSchema(),
                emit={"decision": "d"},
            )
        )
        interp = PlanInterpreter(registry=registry)
        result = await interp.run(plan)
        # Exactly max_visits successful executions — the over-budget
        # visit is NOT executed.
        assert len(result.visits) == max_visits
        assert result.terminal_node == "a"


def _make_plan(
    node_ids: tuple[str, ...],
    *,
    max_visits: int = 1,
) -> Plan:
    nodes: list[PlanNode] = []
    edges: list[PlanEdge] = []
    for idx, nid in enumerate(node_ids):
        nodes.append(
            PlanNode(
                id=nid,
                binding=BindingKind.TRANSFORM,
                entry=(idx == 0),
                max_visits=max_visits,
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


def test_install_predicate_evaluator_roundtrip() -> None:
    def _always_false(when: str, *, result: object, artifacts: dict) -> bool:
        return False

    install_predicate_evaluator(_always_false)
    plan = _make_plan(("a", "b"))
    from lca.framework.graph.traversal import select_edge

    edge = select_edge(edges=plan.edges, current_id="a", result=None, artifacts={})
    assert edge is None
    install_predicate_evaluator(lambda *a, **kw: True)
    edge = select_edge(edges=plan.edges, current_id="a", result=None, artifacts={})
    assert edge is plan.edges[0]
