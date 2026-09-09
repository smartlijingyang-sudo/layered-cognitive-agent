"""Contract tests for ``SubgraphReference`` and the ``PhaseEdge.subgraph_ref`` field.

This is the minimum config-level cut-in for nested-graph references: a
``PhaseEdge`` may now carry an optional ``SubgraphReference`` whose
``binding_edge`` MUST equal the edge's ``source``. The assembler enforces
the two-graph mutual reference at compile time (see
``tests/harness/declarative/test_subgraph_ref_validation.py``).

These tests live in ``tests/contracts/`` because they cover the immutable
dataclass contract (C13) — they do not touch the runtime interpreter or
the assembler.
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
    SemanticPhase,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    PhaseEdge,
    PhaseNode,
    SubgraphReference,
)


class TestSubgraphReferenceConstruction:
    def test_minimal_construction_with_three_required_fields(self) -> None:
        ref = SubgraphReference(
            plan_ref="bundles/reflect-subgraph.yaml",
            entry_node="reflect.inner_score",
            binding_edge="reflect.main",
        )
        assert ref.plan_ref == "bundles/reflect-subgraph.yaml"
        assert ref.entry_node == "reflect.inner_score"
        assert ref.binding_edge == "reflect.main"
        assert ref.return_on == "next"

    def test_return_on_defaults_to_next(self) -> None:
        ref = SubgraphReference(
            plan_ref="x.yaml",
            entry_node="n",
            binding_edge="e",
        )
        assert ref.return_on == "next"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"plan_ref": "", "entry_node": "n", "binding_edge": "e"},
            {"plan_ref": "x", "entry_node": "", "binding_edge": "e"},
            {"plan_ref": "x", "entry_node": "n", "binding_edge": ""},
        ],
    )
    def test_required_fields_must_be_non_empty(self, kwargs: dict[str, str]) -> None:
        with pytest.raises(DeclarativeValidationError) as excinfo:
            SubgraphReference(**kwargs)
        assert excinfo.value.code == "PG-004"

    def test_return_on_must_be_next(self) -> None:
        with pytest.raises(DeclarativeValidationError) as excinfo:
            SubgraphReference(
                plan_ref="x",
                entry_node="n",
                binding_edge="e",
                return_on="skip",
            )
        assert excinfo.value.code == "PG-004"

    def test_is_frozen(self) -> None:
        ref = SubgraphReference(plan_ref="x", entry_node="n", binding_edge="e")
        with pytest.raises((AttributeError, Exception)):
            ref.plan_ref = "y"  # type: ignore[misc]


class TestPhaseEdgeSubgraphRef:
    def test_subgraph_ref_defaults_to_none(self) -> None:
        edge = PhaseEdge(source="think.main", target="act.main", when="true")
        assert edge.subgraph_ref is None

    def test_subgraph_ref_can_be_provided(self) -> None:
        ref = SubgraphReference(
            plan_ref="bundles/reflect-subgraph.yaml",
            entry_node="reflect.inner_score",
            binding_edge="reflect.main",
        )
        edge = PhaseEdge(
            source="reflect.main",
            target="remember.main",
            when="true",
            subgraph_ref=ref,
        )
        assert edge.subgraph_ref is ref
        assert edge.subgraph_ref.binding_edge == edge.source

    def test_subgraph_ref_binding_edge_must_equal_source(self) -> None:
        ref = SubgraphReference(
            plan_ref="bundles/reflect-subgraph.yaml",
            entry_node="reflect.inner_score",
            binding_edge="WRONG",
        )
        with pytest.raises(DeclarativeValidationError) as excinfo:
            PhaseEdge(
                source="reflect.main",
                target="remember.main",
                when="true",
                subgraph_ref=ref,
            )
        assert excinfo.value.code == "PG-004"
        assert "binding_edge" in str(excinfo.value)


class TestPhaseNodeSubSpecRef:
    """Node Note 2026-09-09-phase-node-sub-spec-ref: PhaseNode.sub_spec_ref 节点级
    嵌套子图引用契约。binding_edge 必须 == node.id, 与边级 PG-004 对齐。"""

    def _minimal_node(self, **overrides):
        base = {
            "id": "think.main",
            "semantic_phase": SemanticPhase.THINK,
            "binding": "phase.think.standard",
            "max_visits": 1,
        }
        base.update(overrides)
        return PhaseNode(**base)

    def test_node_accepts_valid_node_level_sub_spec_ref(self):
        ref = SubgraphReference(
            plan_ref="bundles/think-steps.yaml",
            entry_node="think.shortcut",
            binding_edge="think.main",
        )
        node = self._minimal_node(sub_spec_ref=ref)
        assert node.sub_spec_ref is ref
        assert node.sub_spec_ref.binding_edge == node.id

    def test_node_default_sub_spec_ref_is_none(self):
        node = self._minimal_node()
        assert node.sub_spec_ref is None

    def test_node_rejects_sub_spec_ref_with_mismatched_binding_edge(self):
        ref = SubgraphReference(
            plan_ref="bundles/think-steps.yaml",
            entry_node="think.shortcut",
            binding_edge="WRONG",
        )
        with pytest.raises(DeclarativeValidationError) as excinfo:
            self._minimal_node(sub_spec_ref=ref)
        assert excinfo.value.code == "PG-004"
        assert "binding_edge" in str(excinfo.value)
        assert "think.main" in str(excinfo.value)

    def test_node_sub_spec_ref_coexists_with_edge_level_subgraph_ref(self):
        """边级 PhaseEdge.subgraph_ref 与节点级 PhaseNode.sub_spec_ref 是
        正交 seam,interpreter 优先级由实现层决定 (节点级不重复 fork 边级)。"""
        node_ref = SubgraphReference(
            plan_ref="bundles/think-steps.yaml",
            entry_node="think.shortcut",
            binding_edge="think.main",
        )
        edge_ref = SubgraphReference(
            plan_ref="bundles/reflect-subgraph.yaml",
            entry_node="reflect.inner_score",
            binding_edge="reflect.main",
        )
        node = self._minimal_node(sub_spec_ref=node_ref)
        edge = PhaseEdge(
            source="reflect.main",
            target="remember.main",
            when="true",
            subgraph_ref=edge_ref,
        )
        # 两侧引用独立, 不互相影响
        assert node.sub_spec_ref.plan_ref == "bundles/think-steps.yaml"
        assert edge.subgraph_ref.plan_ref == "bundles/reflect-subgraph.yaml"
