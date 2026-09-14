"""Reachability check.

Reject nodes that the entry cannot reach via the edge graph.

A plan with disconnected subgraphs would silently skip those
subgraphs at runtime — they exist in :class:`Plan.nodes` but no
edge sequence ever visits them. Lift-time reachability catches
this so a typo'd edge target or an accidentally orphaned node
fails boot instead of being dead code.

BFS from the plan's entry node; report the unreached nodes
(sorted for stable diffs) as a single :class:`PlanLiftError`.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class ReachabilityCheck(PlanCheck):
    """BFS reachability from the plan entry."""

    check_id = "reachability"
    label = "Reachability (every node reachable from entry)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        if not plan.nodes:
            return None
        entry_id = next((n.id for n in plan.nodes if n.entry), None)
        if entry_id is None:
            return None
        adj: dict[str, list[str]] = {n.id: [] for n in plan.nodes}
        for edge in plan.edges:
            adj.setdefault(edge.source, []).append(edge.target)
        visited: set[str] = {entry_id}
        queue: list[str] = [entry_id]
        while queue:
            cur = queue.pop(0)
            for tgt in adj.get(cur, ()):
                if tgt in visited:
                    continue
                visited.add(tgt)
                queue.append(tgt)
        unreachable = sorted(set(adj.keys()) - visited)
        if unreachable:
            return PlanLiftError(
                f"plan {plan_id!r}: nodes {unreachable!r} are unreachable from "
                f"entry node {entry_id!r}; they will never execute",
                plan_id=plan_id,
            )
        return None


__all__ = ["ReachabilityCheck"]
