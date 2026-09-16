"""Tests for the Plan SDK — typed construction, serialization, round-trip.

Dispatch 6 of the typed port graph redesign. Validates that:
- Convenience builders return typed Pydantic models (not raw dicts).
- Predicate factories produce correct Predicate structures.
- serialize_plan produces v2 BundleGraphSpec YAML.
- parse_plan_yaml round-trips through serialize preserving typed Predicate.
"""

from __future__ import annotations

import yaml

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan
from lca.contracts.protocols.graph.predicate import PortRef, Predicate
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.framework.graph.plan_sdk import (
    and_,
    edge,
    eq,
    exists,
    in_,
    missing,
    ne,
    node,
    not_,
    or_,
    parse_plan_yaml,
    plan,
    port,
    routing,
    serialize_plan,
)

# ---------------------------------------------------------------------------
# Predicate factory tests
# ---------------------------------------------------------------------------


class TestPredicateFactories:
    def test_eq_produces_leaf_predicate(self) -> None:
        p = eq(port("decision"), "use_tool")
        assert isinstance(p, Predicate)
        assert p.kind == "eq"
        assert p.port == PortRef(name="decision")
        assert p.value == "use_tool"
        assert p.children == ()

    def test_eq_with_field(self) -> None:
        ref = port("decision")
        p = eq(
            PortRef(name=ref.name, field="action_type"),
            "use_tool",
        )
        assert p.port is not None
        assert p.port.name == "decision"
        assert p.port.field == "action_type"
        assert p.value == "use_tool"

    def test_ne_produces_leaf_predicate(self) -> None:
        p = ne(port("response"), "")
        assert p.kind == "ne"
        assert p.value == ""

    def test_in_produces_leaf_predicate(self) -> None:
        p = in_(port("decision"), ["use_tool", "respond"])
        assert p.kind == "in"
        assert p.value == ["use_tool", "respond"]

    def test_exists_produces_leaf_predicate(self) -> None:
        p = exists(port("decision"))
        assert p.kind == "exists"
        assert p.port == PortRef(name="decision")
        assert p.value is None

    def test_missing_produces_leaf_predicate(self) -> None:
        p = missing(port("response"))
        assert p.kind == "missing"

    def test_and_produces_nested_predicate(self) -> None:
        p1 = eq(PortRef(name="decision", field="action_type"), "respond")
        p2 = ne(PortRef(name="decision", field="response"), "")
        combined = and_(p1, p2)
        assert combined.kind == "and"
        assert len(combined.children) == 2
        assert combined.children[0] == p1
        assert combined.children[1] == p2

    def test_or_produces_nested_predicate(self) -> None:
        p1 = eq(port("decision"), "use_tool")
        p2 = eq(port("decision"), "respond")
        combined = or_(p1, p2)
        assert combined.kind == "or"
        assert len(combined.children) == 2

    def test_not_produces_single_child_predicate(self) -> None:
        p = eq(port("decision"), "stop")
        negated = not_(p)
        assert negated.kind == "not"
        assert len(negated.children) == 1
        assert negated.children[0] == p

    def test_deeply_nested_predicate(self) -> None:
        p = and_(
            or_(
                eq(PortRef(name="decision", field="action_type"), "use_tool"),
                eq(PortRef(name="decision", field="action_type"), "delegate"),
            ),
            not_(eq(PortRef(name="decision", field="action_type"), "stop")),
        )
        assert p.kind == "and"
        assert p.children[0].kind == "or"
        assert p.children[1].kind == "not"


# ---------------------------------------------------------------------------
# Port / routing / node / edge builder tests
# ---------------------------------------------------------------------------


class TestBuilders:
    def test_port_returns_port_ref(self) -> None:
        ref = port("decision")
        assert isinstance(ref, PortRef)
        assert ref.name == "decision"
        assert ref.field is None

    def test_port_with_payload_type_accepted(self) -> None:
        """payload_type is accepted for forward compatibility."""

        class _FakePayload:
            pass

        ref = port("decision", payload_type=_FakePayload)
        assert ref.name == "decision"

    def test_routing_returns_typed_decision(self) -> None:
        r = routing(ActionType.USE_TOOL)
        assert isinstance(r, RoutingDecision)
        assert r.action_type == ActionType.USE_TOOL
        assert r.should_terminate is False
        assert r.next_hint is None

    def test_routing_with_string_action_type(self) -> None:
        r = routing("respond", should_terminate=True, next_hint="done")
        assert r.action_type == ActionType.RESPOND
        assert r.should_terminate is True
        assert r.next_hint == "done"

    def test_node_returns_plan_node(self) -> None:
        n = node("think", BindingKind.NODE_EXECUTOR)
        assert n.id == "think"
        assert n.binding == BindingKind.NODE_EXECUTOR
        assert isinstance(n.io_schema, NodeIOSchema)

    def test_node_with_string_binding(self) -> None:
        n = node("t", "subgraph")
        assert n.binding == BindingKind.SUBGRAPH

    def test_node_with_io_schema(self) -> None:
        n = node(
            "classify",
            "node_executor",
            inputs=[PortSpec(name="response")],
            outputs=[PortSpec(name="decision")],
        )
        assert n.io_schema.inputs == (PortSpec(name="response"),)
        assert n.io_schema.outputs == (PortSpec(name="decision"),)

    def test_edge_returns_plan_edge(self) -> None:
        e = edge("a", "b")
        assert e.source == "a"
        assert e.target == "b"
        assert e.when is None  # D4: None means "always true"

    def test_edge_with_predicate(self) -> None:
        pred = eq(port("decision"), "use_tool")
        e = edge("think", "act", when=pred)
        assert isinstance(e.when, Predicate)
        assert e.when == pred

    def test_plan_validates_entry(self) -> None:
        p = plan(
            "test",
            nodes=[
                node("a", "node_executor", entry=True),
                node("b", "node_executor"),
            ],
        )
        assert p.id == "test"
        assert len(p.nodes) == 2


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


def _build_test_plan() -> Plan:
    """Build a minimal plan for serialization testing."""
    think_node = node(
        "think",
        "node_executor",
        outputs=[PortSpec(name="decision")],
        entry=True,
    )
    act_node = node(
        "act",
        "node_executor",
        inputs=[PortSpec(name="decision")],
        outputs=[PortSpec(name="act_outcome")],
    )
    terminal_node = node(
        "terminal",
        "terminate",
        inputs=[PortSpec(name="decision"), PortSpec(name="act_outcome")],
        terminal=True,
    )
    return plan(
        "test.plan",
        nodes=[think_node, act_node, terminal_node],
        edges=[
            edge(
                "think",
                "act",
                when=eq(PortRef(name="decision", field="action_type"), "use_tool"),
            ),
            edge(
                "think",
                "terminal",
                when=and_(
                    eq(PortRef(name="decision", field="action_type"), "respond"),
                    ne(PortRef(name="decision", field="response"), ""),
                ),
            ),
            edge("act", "terminal", when=exists(port("act_outcome"))),
        ],
    )


class TestSerialize:
    def test_serialize_produces_valid_yaml(self) -> None:
        p = _build_test_plan()
        text = serialize_plan(p)
        doc = yaml.safe_load(text)
        assert doc["id"] == "test.plan"
        assert len(doc["nodes"]) == 3
        assert len(doc["edges"]) == 3

    def test_serialize_node_shape(self) -> None:
        p = _build_test_plan()
        doc = yaml.safe_load(serialize_plan(p))
        think = doc["nodes"][0]
        assert think["id"] == "think"
        assert think["binding"] == "node_executor"
        assert think["entry"] is True
        assert "outputs" in think["io_schema"]

    def test_serialize_edge_structured_predicate(self) -> None:
        p = _build_test_plan()
        doc = yaml.safe_load(serialize_plan(p))
        edge0 = doc["edges"][0]
        assert edge0["from"] == "think"
        assert edge0["to"] == "act"
        assert edge0["when"]["kind"] == "eq"
        assert edge0["when"]["port"]["name"] == "decision"
        assert edge0["when"]["port"]["field"] == "action_type"
        assert edge0["when"]["value"] == "use_tool"

    def test_serialize_edge_compound_predicate(self) -> None:
        p = _build_test_plan()
        doc = yaml.safe_load(serialize_plan(p))
        edge1 = doc["edges"][1]
        when = edge1["when"]
        assert when["kind"] == "and"
        assert len(when["children"]) == 2
        assert when["children"][0]["kind"] == "eq"
        assert when["children"][1]["kind"] == "ne"


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_round_trip_preserves_plan_identity(self) -> None:
        p = _build_test_plan()
        text = serialize_plan(p)
        p2 = parse_plan_yaml(text)
        assert p2.id == p.id
        assert len(p2.nodes) == len(p.nodes)
        assert len(p2.edges) == len(p.edges)

    def test_round_trip_preserves_node_fields(self) -> None:
        p = _build_test_plan()
        p2 = parse_plan_yaml(serialize_plan(p))
        for orig, parsed in zip(p.nodes, p2.nodes, strict=True):
            assert parsed.id == orig.id
            assert parsed.binding == orig.binding
            assert parsed.terminal == orig.terminal
            assert parsed.entry == orig.entry

    def test_round_trip_preserves_io_schema(self) -> None:
        p = _build_test_plan()
        p2 = parse_plan_yaml(serialize_plan(p))
        for orig, parsed in zip(p.nodes, p2.nodes, strict=True):
            assert len(parsed.io_schema.inputs) == len(orig.io_schema.inputs)
            assert len(parsed.io_schema.outputs) == len(orig.io_schema.outputs)
            for oi, pi in zip(orig.io_schema.inputs, parsed.io_schema.inputs, strict=True):
                assert pi.name == oi.name
            for oo, po in zip(orig.io_schema.outputs, parsed.io_schema.outputs, strict=True):
                assert po.name == oo.name

    def test_round_trip_preserves_predicate_when(self) -> None:
        """The critical test: when must be a Predicate, not a string."""
        p = _build_test_plan()
        p2 = parse_plan_yaml(serialize_plan(p))
        for orig, parsed in zip(p.edges, p2.edges, strict=True):
            assert isinstance(parsed.when, Predicate)
            assert isinstance(orig.when, Predicate)
            assert parsed.when == orig.when

    def test_round_trip_complex_predicate(self) -> None:
        pred = and_(
            or_(
                eq(PortRef(name="decision", field="action_type"), "use_tool"),
                eq(PortRef(name="decision", field="action_type"), "delegate"),
            ),
            not_(eq(PortRef(name="decision", field="action_type"), "stop")),
            exists(port("response")),
        )
        p = plan(
            "complex",
            nodes=[
                node(
                    "a",
                    "node_executor",
                    entry=True,
                    outputs=[
                        PortSpec(name="decision"),
                        PortSpec(name="response"),
                    ],
                ),
                node("b", "node_executor", terminal=True),
            ],
            edges=[edge("a", "b", when=pred)],
        )
        p2 = parse_plan_yaml(serialize_plan(p))
        assert isinstance(p2.edges[0].when, Predicate)
        assert p2.edges[0].when == pred

    def test_round_trip_simple_leaf_predicates(self) -> None:
        """Every leaf kind survives serialize → parse."""
        ref = port("decision")
        preds = [
            eq(ref, "use_tool"),
            ne(ref, ""),
            in_(ref, ["a", "b"]),
            exists(ref),
            missing(ref),
        ]
        for pred in preds:
            p = plan(
                "leaf",
                nodes=[
                    node(
                        "x",
                        "node_executor",
                        entry=True,
                        outputs=[PortSpec(name="decision")],
                    ),
                    node("y", "node_executor", terminal=True),
                ],
                edges=[edge("x", "y", when=pred)],
            )
            p2 = parse_plan_yaml(serialize_plan(p))
            assert p2.edges[0].when == pred, f"failed for kind={pred.kind}"

    def test_serialize_then_parse_is_idempotent(self) -> None:
        """serialize → parse → serialize produces identical YAML."""
        p = _build_test_plan()
        yaml1 = serialize_plan(p)
        yaml2 = serialize_plan(parse_plan_yaml(yaml1))
        assert yaml1 == yaml2
