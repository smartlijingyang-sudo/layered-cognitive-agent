"""plan_lift.strip_complete_when_no_llm tests (ADR-0219 §10.11 item 2).

Contract:
- When strip_complete_when_no_llm=True, think.reason.complete is removed
  from the lifted spec's nodes, and its incoming edge is dropped too.
- When strip_complete_when_no_llm=False (default), the spec is unchanged.
- When the spec does not contain think.reason.complete, the spec is
  returned unchanged.
- The result is a NEW BundleGraphSpec instance (frozen dataclass via
  dataclasses.replace).
"""

from __future__ import annotations

from typing import Any

from lca.framework.subgraph.plugins.plan_lift import lift_subgraph_reference_to_v2
from lca.harness.declarative.compile.subgraph_resolver import (
    _load_bundle_graph_spec,
)


class _FakePlan:
    """V2 marker plan returning a given spec from get_bundle_graph_spec."""

    def __init__(self, spec: Any) -> None:
        self._spec = spec

    def get_bundle_graph_spec(self) -> Any:
        return self._spec


class TestStripCompleteWhenNoLlm:
    def test_default_flag_keeps_complete(self) -> None:
        spec = _load_bundle_graph_spec("bundles/think_reason.yaml")
        plan = _FakePlan(spec)
        lifted = lift_subgraph_reference_to_v2(
            ref=None,  # type: ignore[arg-type]
            sub_plan_obj=plan,
        )
        ids = [n.id for n in lifted.nodes]
        assert "think.reason.complete" in ids

    def test_strip_true_removes_complete_node(self) -> None:
        spec = _load_bundle_graph_spec("bundles/think_reason.yaml")
        plan = _FakePlan(spec)
        lifted = lift_subgraph_reference_to_v2(
            ref=None,  # type: ignore[arg-type]
            sub_plan_obj=plan,
            strip_complete_when_no_llm=True,
        )
        ids = [n.id for n in lifted.nodes]
        assert "think.reason.complete" not in ids
        # remaining 2 nodes
        assert set(ids) == {"think.reason.plan", "think.reason.render"}

    def test_strip_true_drops_incoming_edge_to_complete(self) -> None:
        spec = _load_bundle_graph_spec("bundles/think_reason.yaml")
        plan = _FakePlan(spec)
        lifted = lift_subgraph_reference_to_v2(
            ref=None,  # type: ignore[arg-type]
            sub_plan_obj=plan,
            strip_complete_when_no_llm=True,
        )
        edge_targets = [e.target for e in lifted.edges]
        assert "think.reason.complete" not in edge_targets

    def test_strip_returns_new_spec_instance(self) -> None:
        spec = _load_bundle_graph_spec("bundles/think_reason.yaml")
        plan = _FakePlan(spec)
        lifted = lift_subgraph_reference_to_v2(
            ref=None,  # type: ignore[arg-type]
            sub_plan_obj=plan,
            strip_complete_when_no_llm=True,
        )
        assert lifted is not spec

    def test_strip_is_noop_when_complete_absent(self) -> None:
        # Build a 2-node spec without think.reason.complete
        from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
            BundleGraphEdge,
            BundleGraphNode,
            BundleGraphSpec,
        )

        nodes = (
            BundleGraphNode(
                id="think.reason.plan",
                region="phase:think",
                factory="think.reason.plan",
                config={"max_visits": 1},
            ),
            BundleGraphNode(
                id="think.reason.render",
                region="phase:think",
                factory="think.reason.render",
                config={"max_visits": 1},
            ),
        )
        edges = (
            BundleGraphEdge(
                source="think.reason.plan",
                target="think.reason.render",
            ),
        )
        spec = BundleGraphSpec(
            id="no-complete",
            region="phase:think",
            purpose="test",
            nodes=nodes,
            edges=edges,
            entry="think.reason.plan",
        )
        plan = _FakePlan(spec)
        lifted = lift_subgraph_reference_to_v2(
            ref=None,  # type: ignore[arg-type]
            sub_plan_obj=plan,
            strip_complete_when_no_llm=True,
        )
        # No-op: same nodes, same edges
        assert [n.id for n in lifted.nodes] == ["think.reason.plan", "think.reason.render"]
        assert list(lifted.edges) == list(spec.edges)
