"""Tests for PR-1 graph protocols subpackage.

Pure protocol-level tests. No graph kernel, no interpreter, no plugin.
The goal: every shape contract is locked at the pydantic boundary so
later PRs (kernel, strategies, lifter) can depend on these invariants.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.protocols.graph import (
    BindingKind,
    DispatchDecision,
    NodeInput,
    NodeIOSchema,
    NodeOutput,
    NodeSchemaError,
    Plan,
    PlanEdge,
    PlanNode,
    PortSpec,
    SubgraphReference,
    VisitRecord,
)


class TestPortSpec:
    def test_name_is_required(self) -> None:
        with pytest.raises(ValidationError):
            PortSpec()

    def test_required_defaults_true(self) -> None:
        spec = PortSpec(name="decision")
        assert spec.required is True

    def test_forbidden_extra(self) -> None:
        with pytest.raises(ValidationError):
            PortSpec(name="decision", unknown=1)


class TestNodeIOSchema:
    def test_duplicate_names_fail_loud(self) -> None:
        with pytest.raises(ValidationError):
            NodeIOSchema(
                inputs=(PortSpec(name="decision"),),
                outputs=(PortSpec(name="decision"),),
            )

    def test_required_inputs(self) -> None:
        schema = NodeIOSchema(
            inputs=(
                PortSpec(name="decision", required=True),
                PortSpec(name="observation", required=False),
            ),
            outputs=(PortSpec(name="response"),),
        )
        assert schema.required_inputs() == ("decision",)
        assert schema.output_names() == frozenset({"response"})

    def test_satisfied_by(self) -> None:
        schema = NodeIOSchema(
            inputs=(PortSpec(name="decision", required=True),),
        )
        assert schema.satisfied_by({"decision": object()})
        assert not schema.satisfied_by({})

    def test_project_outputs_rejects_unknown(self) -> None:
        schema = NodeIOSchema(outputs=(PortSpec(name="observation"),))
        with pytest.raises(NodeSchemaError):
            schema.project_outputs({"observation": 1, "extra": 2})


class TestNodeInput:
    def test_require_raises_with_context(self) -> None:
        node_input = NodeInput(port_values={"decision": 1}, consumer_node="a")
        assert node_input.require("decision") == 1
        with pytest.raises(NodeSchemaError) as exc:
            node_input.require("response")
        assert "consumer_node='a'" in str(exc.value)
        assert "response" in str(exc.value)

    def test_get_returns_default(self) -> None:
        node_input = NodeInput()
        assert node_input.get("anything", "fallback") == "fallback"


class TestNodeOutput:
    def test_producer_node_field(self) -> None:
        out = NodeOutput(producer_node="b")
        assert out.producer_node == "b"
        assert out.next_hint is None


class TestBindingKind:
    def test_nine_entries(self) -> None:
        assert len(BindingKind) == 9

    def test_all_values_are_strings(self) -> None:
        for kind in BindingKind:
            assert isinstance(kind.value, str)


class TestSubgraphReference:
    def test_required_fields(self) -> None:
        ref = SubgraphReference(plan_ref="a.yaml", entry_node="x", binding_edge="y")
        assert ref.plan_ref == "a.yaml"
        assert ref.entry_node == "x"
        assert ref.binding_edge == "y"
        assert ref.return_on == "next"


class TestPlanNode:
    def test_max_visits_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            PlanNode(id="n", binding=BindingKind.NODE_EXECUTOR, max_visits=0)

    def test_default_values(self) -> None:
        n = PlanNode(id="n", binding=BindingKind.NODE_EXECUTOR)
        assert n.max_visits == 1
        assert n.terminal is False
        assert n.entry is False
        assert n.io_schema == NodeIOSchema()


class TestPlanEdge:
    def test_default_when_is_true(self) -> None:
        e = PlanEdge(source="a", target="b")
        assert e.when == "true"


class TestPlan:
    def _node(self, id_: str, *, entry: bool = False) -> PlanNode:
        return PlanNode(id=id_, binding=BindingKind.NODE_EXECUTOR, entry=entry)

    def test_exactly_one_entry_required(self) -> None:
        with pytest.raises(ValidationError):
            Plan(id="p", nodes=(self._node("a"), self._node("b")))
        with pytest.raises(ValidationError):
            Plan(
                id="p",
                nodes=(self._node("a", entry=True), self._node("b", entry=True)),
            )

    def test_edge_must_reference_known_nodes(self) -> None:
        with pytest.raises(ValidationError):
            Plan(
                id="p",
                nodes=(self._node("a", entry=True),),
                edges=(PlanEdge(source="a", target="ghost"),),
            )

    def test_outgoing_filter(self) -> None:
        p = Plan(
            id="p",
            nodes=(
                self._node("a", entry=True),
                self._node("b"),
                self._node("c"),
            ),
            edges=(
                PlanEdge(source="a", target="b"),
                PlanEdge(source="b", target="c"),
                PlanEdge(source="a", target="c"),
            ),
        )
        assert {e.target for e in p.outgoing("a")} == {"b", "c"}
        assert {e.target for e in p.outgoing("b")} == {"c"}


class TestVisitRecord:
    def test_dispatch_kind_choices(self) -> None:
        d = DispatchDecision(kind="next", next_node="x")
        assert d.kind == "next"

    def test_record_carries_inputs_outputs(self) -> None:
        r = VisitRecord(
            plan_ref="p",
            node_id="n",
            binding_kind=BindingKind.NODE_EXECUTOR,
            inputs={"decision": 1},
            outputs={"observation": 2},
            dispatch=DispatchDecision(kind="terminal"),
        )
        assert r.inputs["decision"] == 1
        assert r.outputs["observation"] == 2
        assert r.sub_call_chain == ()


class TestBarrelReexport:
    def test_re_exports(self) -> None:
        from lca.contracts import protocols

        for name in (
            "BindingKind",
            "DispatchDecision",
            "NodeInput",
            "NodeIOSchema",
            "NodeOutput",
            "NodeSchemaError",
            "NodeStrategy",
            "Plan",
            "PlanEdge",
            "PlanNode",
            "PortSpec",
            "StrategyContext",
            "GraphSubgraphReference",
            "VisitRecord",
        ):
            assert name in protocols.__all__, f"missing {name} from protocols.__all__"
            assert hasattr(protocols, name), f"missing {name} on protocols"