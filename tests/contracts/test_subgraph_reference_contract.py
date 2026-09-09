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
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    PhaseEdge,
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
