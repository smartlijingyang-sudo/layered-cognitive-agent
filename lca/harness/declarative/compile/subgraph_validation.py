"""Compile-time validation for ``PhaseEdge.subgraph_ref`` references.

The validation enforces the two-graph mutual-reference invariant: an
outer edge that points at a subgraph plan (``SubgraphReference``) MUST
be matched by at least one edge in the subgraph whose own
``subgraph_ref.plan_ref`` names the outer edge's ``source``. Both sides
of the reference are checked at compile time; an asymmetric reference
is rejected with ``DeclarativeValidationError("PG-004", ...)``.

GraphAssembler is retired (ADR-0221 P3); this validator is the remaining
compile-time seam for PG-004 and accepts duck-typed plans that expose
``phase_graph``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    PhaseEdge,
    SubgraphReference,
)


@runtime_checkable
class SubgraphResolver(Protocol):
    """Minimal resolver Protocol used by PG-004 validation."""

    def resolve(self, plan_ref: str) -> object | None: ...


def validate_subgraph_references(
    plan: object,
    resolver: SubgraphResolver,
) -> None:
    """Walk every edge with a ``subgraph_ref`` and enforce the PG-004 invariants."""
    graph = getattr(plan, "phase_graph", None)
    if graph is None:
        return
    for edge in graph.edges:
        ref = edge.subgraph_ref
        if ref is None:
            continue
        _validate_one_reference(edge, ref, resolver)


def _validate_one_reference(
    edge: PhaseEdge,
    ref: SubgraphReference,
    resolver: SubgraphResolver,
) -> None:
    """Enforce PG-004 for one outer-edge ↔ subgraph pair."""
    sub_plan = resolver.resolve(ref.plan_ref)
    if sub_plan is None:
        raise DeclarativeValidationError(
            "PG-004",
            f"edge {edge.source!r} subgraph_ref.plan_ref {ref.plan_ref!r} could not be resolved",
        )
    if not hasattr(sub_plan, "phase_graph"):
        raise DeclarativeValidationError(
            "PG-004",
            f"edge {edge.source!r} subgraph_ref.plan_ref "
            f"{ref.plan_ref!r} resolved to non-plan value "
            f"{type(sub_plan).__name__}",
        )
    sub_graph = getattr(sub_plan, "phase_graph", None)
    if sub_graph is None:
        raise DeclarativeValidationError(
            "PG-004",
            f"edge {edge.source!r} subgraph_ref.plan_ref "
            f"{ref.plan_ref!r} resolved to a plan with no phase graph",
        )
    sub_node_ids = {node.id for node in sub_graph.nodes}
    if ref.entry_node not in sub_node_ids:
        raise DeclarativeValidationError(
            "PG-004",
            f"edge {edge.source!r} subgraph_ref.entry_node "
            f"{ref.entry_node!r} not present in referenced plan {ref.plan_ref!r}; "
            f"declared nodes: {sorted(sub_node_ids)}",
        )
    has_back_reference = any(
        back_edge.subgraph_ref is not None and back_edge.subgraph_ref.plan_ref == edge.source
        for back_edge in sub_graph.edges
    )
    if not has_back_reference:
        raise DeclarativeValidationError(
            "PG-004",
            f"edge {edge.source!r} subgraph_ref requires the referenced plan "
            f"{ref.plan_ref!r} to declare a back-reference edge whose "
            f"subgraph_ref.plan_ref equals {edge.source!r}",
        )


__all__ = ["SubgraphResolver", "validate_subgraph_references"]
