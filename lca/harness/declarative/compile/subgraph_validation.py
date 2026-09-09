"""Compile-time validation for ``PhaseEdge.subgraph_ref`` references.

The validation enforces the two-graph mutual-reference invariant: an
outer edge that points at a subgraph plan (``SubgraphReference``) MUST
be matched by at least one edge in the subgraph whose own
``subgraph_ref.plan_ref`` names the outer edge's ``source``. Both sides
of the reference are checked at compile time; an asymmetric reference
is rejected with ``DeclarativeValidationError("PG-004", ...)``.

This module owns no I/O — it takes a ``SubgraphResolver`` Protocol and
a ``CompiledRunPlan``, walks the outer graph's edges once, and raises
on the first violation. The default bundle-relative resolver lives
sibling-side in `lca.harness.declarative.compile.subgraph_resolver`;
tests substitute a hand-built stub.
"""

from __future__ import annotations

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    PhaseEdge,
    SubgraphReference,
    SubgraphResolver,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan


def validate_subgraph_references(
    plan: CompiledRunPlan,
    resolver: SubgraphResolver,
) -> None:
    """Walk every edge with a ``subgraph_ref`` and enforce the PG-004 invariants.

    For each such edge the function resolves the referenced plan, asserts
    that the named ``entry_node`` exists in the subgraph, and asserts
    that the subgraph declares at least one back-reference edge whose
    ``subgraph_ref.plan_ref`` equals the outer edge's ``source``.

    Plans without any ``subgraph_ref``-bearing edge are returned
    unchanged — the caller's resolver is not invoked.
    """
    graph = plan.phase_graph
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
    if not isinstance(sub_plan, CompiledRunPlan):
        raise DeclarativeValidationError(
            "PG-004",
            f"edge {edge.source!r} subgraph_ref.plan_ref "
            f"{ref.plan_ref!r} resolved to non-plan value "
            f"{type(sub_plan).__name__}",
        )
    sub_graph = sub_plan.phase_graph
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
    # Mutual-reference check: the referenced plan must name the outer
    # edge id in at least one back-edge's ``subgraph_ref.plan_ref``.
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


__all__ = ["validate_subgraph_references"]
