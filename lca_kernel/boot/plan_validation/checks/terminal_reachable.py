"""Terminal reachability check.

Reject plans where no terminal node is reachable from the entry.

The kernel terminates when it visits a node with ``terminal=True``
(or when a node's ``terminal_predicate`` fires). If the BFS from
the plan entry never reaches such a node the kernel runs forever
(the classic "infinite loop" graph bug — see e.g. Cordis /
react-flow / igraph stack traces). Catch the unreachable-termination
case at boot time.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class TerminalReachableCheck(PlanCheck):
    """At least one terminal node must be reachable from the entry."""

    check_id = "terminal_reachable"
    label = "Terminal reachable from entry (no infinite run)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        entry_id = next((n.id for n in plan.nodes if n.entry), None)
        if entry_id is None:
            return None
        terminals = {
            n.id
            for n in plan.nodes
            if n.terminal or n.io_schema.terminal_predicate is not None
        }
        if not terminals:
            # ``_check_lifted_plan``'s reachability + lifter's
            # ``_validate_termination`` already cover the no-terminal
            # case; skip here to avoid double-reporting.
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
        if not (terminals & visited):
            terminal_list = sorted(terminals)
            return PlanLiftError(
                f"plan {plan_id!r}: terminal nodes {terminal_list!r} are "
                f"unreachable from entry {entry_id!r}; the kernel will "
                f"run forever instead of terminating. Add an edge from "
                f"some reachable node to a terminal, or mark a reachable "
                f"node ``terminal: true``.",
                plan_id=plan_id,
            )
        return None


__all__ = ["TerminalReachableCheck"]
