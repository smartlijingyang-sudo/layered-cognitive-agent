"""Lift interface surface — callers hit PlanLifter / module API only.

Step #1 of framework-graph deepen: parsers + validators live behind
the Lift interface; tests assert parity through that seam.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.predicate import Predicate
from lca.framework.graph.lift import (
    DefaultPlanLifter,
    PlanLifter,
    get_plan_lifter,
    lift_graph_spec,
)
from lca.framework.graph.lifter import lift_graph_spec as lift_from_facade
from lca.framework.graph.plan_sdk import lift_via_interface, parse_plan_yaml, serialize_plan

REPO = Path(__file__).resolve().parents[3]
OUTER = REPO / "bundles" / "outer" / "phase_main.yaml"


class TestLiftInterface:
    def test_stable_facade_matches_package(self) -> None:
        """``lca.framework.graph.lifter`` keeps stable import paths."""
        assert lift_from_facade is lift_graph_spec

    def test_get_plan_lifter_is_protocol(self) -> None:
        lifter = get_plan_lifter()
        assert isinstance(lifter, PlanLifter)
        assert isinstance(lifter, DefaultPlanLifter)

    def test_phase_main_outer_lifts_via_interface(self) -> None:
        spec = yaml.safe_load(OUTER.read_text(encoding="utf-8"))
        plan = get_plan_lifter().lift_graph_spec(spec)
        assert plan.id == "phase.main.outer"
        via_sdk = lift_via_interface(spec)
        assert via_sdk.id == plan.id
        assert len(via_sdk.nodes) == len(plan.nodes)

    def test_predicate_validation_fail_loud_via_interface(self) -> None:
        spec = {
            "id": "bad_pred",
            "nodes": [
                {
                    "id": "a",
                    "binding": "node_executor",
                    "outputs": ["decision"],
                    "entry": True,
                },
                {"id": "b", "binding": "node_executor", "terminal": True},
            ],
            "edges": [
                {
                    "from": "a",
                    "to": "b",
                    "when": {
                        "kind": "eq",
                        "port": {"name": "missing_port"},
                        "value": "x",
                    },
                }
            ],
        }
        with pytest.raises(PlanLiftError) as ei:
            lift_via_interface(spec)
        assert ei.value.port_name == "missing_port"

    def test_sdk_serialize_parse_uses_lift(self) -> None:
        """parse_plan_yaml routes through Lift (nested io_schema accepted)."""
        from lca.contracts.protocols.graph.node_io import PortSpec
        from lca.framework.graph.plan_sdk import edge, eq, node, plan, port

        p = plan(
            "sdk.round",
            nodes=[
                node(
                    "a",
                    "node_executor",
                    entry=True,
                    outputs=[PortSpec(name="decision")],
                ),
                node("b", "node_executor", terminal=True),
            ],
            edges=[edge("a", "b", when=eq(port("decision"), "use_tool"))],
        )
        p2 = parse_plan_yaml(serialize_plan(p))
        assert isinstance(p2.edges[0].when, Predicate)
        assert p2.edges[0].when == p.edges[0].when
