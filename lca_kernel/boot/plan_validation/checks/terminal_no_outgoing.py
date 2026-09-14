"""Terminal sink check.

Reject ``terminal=True`` nodes with outgoing edges.

A terminal node is meant to be a sink — once the kernel visits it
the plan completes. Outgoing edges from a terminal node are dead
code (the kernel never traverses them) and confuse the static
graph view (operators see a "transition" that never fires).
Subgraph delegate nodes are exempt because their ``binding_edge``
re-enters the outer caller, not a downstream node in the same
plan.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class TerminalNoOutgoingEdgesCheck(PlanCheck):
    """Terminal nodes must be sinks (no outgoing edges in the same plan)."""

    check_id = "terminal_no_outgoing_edges"
    label = "Terminal nodes have no outgoing edges"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        for node in plan.nodes:
            if not node.terminal:
                continue
            if node.subgraph_ref is not None:
                continue
            outgoing = [e for e in plan.edges if e.source == node.id]
            if outgoing:
                return PlanLiftError(
                    f"plan {plan_id!r}: terminal node {node.id!r} has "
                    f"{len(outgoing)} outgoing edge(s); terminal nodes "
                    f"are sinks and their edges never fire. Mark the "
                    f"target node as the terminal or remove the edges.",
                    plan_id=plan_id,
                    node_id=node.id,
                )
        return None


__all__ = ["TerminalNoOutgoingEdgesCheck"]
