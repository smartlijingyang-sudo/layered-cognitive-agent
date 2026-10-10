"""Scenario test for parallel tool calls traversing act_subgraph.

Verifies Invariant INV-PARALLEL-01:
When multiple tool calls are emitted by Cognition, act.fanout routes
``routing.next_hint = 'fanout_ntom'``, and act_subgraph routes to
``effect.pre_dispatch.envelope_check`` without dropping edges or terminating prematurely.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.protocols.graph.plan import Plan
from lca.contracts.protocols.graph.predicate import Predicate
from lca.framework.graph.lifter import _lift_graph_spec_inner, validate_predicates
from lca.framework.graph.predicate_evaluator import evaluate_predicate

BUNDLE_PATH = Path("bundles/act/act_subgraph.yaml")


def _apply_entry_fallback(mapping: Mapping[str, Any]) -> dict[str, Any]:
    spec = dict(mapping)
    nodes = list(spec.get("nodes") or ())
    if nodes and not any(isinstance(n, dict) and n.get("entry") for n in nodes):
        nodes[0] = {**nodes[0], "entry": True}
        spec["nodes"] = nodes
    return spec


def _lift_act_bundle() -> Plan:
    assert BUNDLE_PATH.exists(), f"bundle not found at {BUNDLE_PATH}"
    raw = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))
    spec = _apply_entry_fallback(raw)
    plan = _lift_graph_spec_inner(spec)
    validate_predicates(plan)
    return plan


def test_act_subgraph_routes_fanout_ntom():
    """INV-PARALLEL-01: act.fanout -> effect.pre_dispatch.envelope_check edge must
    accept both fanout_1to1 and fanout_ntom hints.
    """
    plan = _lift_act_bundle()
    edge = next(
        (
            e
            for e in plan.edges
            if e.source == "act.fanout" and e.target == "effect.pre_dispatch.envelope_check"
        ),
        None,
    )
    assert edge is not None, (
        "act_subgraph must wire an edge from act.fanout to effect.pre_dispatch.envelope_check"
    )
    assert isinstance(edge.when, Predicate), (
        f"act.fanout -> envelope_check predicate must be a typed Predicate, got {type(edge.when)}"
    )

    # Edge predicate must match both fanout_1to1 and fanout_ntom
    assert edge.when.port is not None and edge.when.port.name == "routing"
    assert edge.when.port.field == "next_hint"

    class SimplePortReader:
        def __init__(self, port_values: dict[str, dict[str, str]]):
            self._values = port_values

        def read(self, port_ref):
            node_dict = self._values.get(port_ref.name, {})
            if port_ref.field:
                return node_dict[port_ref.field]
            return node_dict

        def port_has_value(self, port_name: str) -> bool:
            return port_name in self._values

    # Test fanout_1to1 matches
    reader_1to1 = SimplePortReader({"routing": {"next_hint": "fanout_1to1"}})
    assert evaluate_predicate(edge.when, reader=reader_1to1) is True

    # Test fanout_ntom matches (INV-PARALLEL-01)
    reader_ntom = SimplePortReader({"routing": {"next_hint": "fanout_ntom"}})
    assert evaluate_predicate(edge.when, reader=reader_ntom) is True

    # Test unexpected hint does not match
    reader_other = SimplePortReader({"routing": {"next_hint": "fanout_other"}})
    assert evaluate_predicate(edge.when, reader=reader_other) is False
