"""Cycle-has-terminal check.

Reject strongly connected components (cycles) that contain no
terminal node.  A cycle without a terminal is an infinite-loop
trap — the interpreter enters the cycle and dead-ends with no
termination signal.  After ADR-0225, the prior ``max_visits``
per-node ceiling no longer fires to break runaway cycles, so this
check is the runtime guard against cycles that have no exit.

The check uses an iterative Tarjan SCC algorithm to avoid
recursion limits on large graphs.  Single-node SCCs are skipped
(self-loops are now safe via per-node ``terminal_predicate``).
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class CycleHasTerminalCheck(PlanCheck):
    """Every non-trivial SCC must contain at least one terminal node."""

    check_id = "cycle_has_terminal"
    label = "Cycle contains terminal (no infinite loop trap)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        """Return a :class:`PlanLiftError` if any SCC of size > 1 has no terminal."""
        node_ids = [n.id for n in plan.nodes]
        if not node_ids:
            return None

        index_of = {nid: i for i, nid in enumerate(node_ids)}
        adj: list[list[int]] = [[] for _ in node_ids]
        for edge in plan.edges:
            if edge.source in index_of and edge.target in index_of:
                adj[index_of[edge.source]].append(index_of[edge.target])

        terminals = {
            index_of[n.id]
            for n in plan.nodes
            if n.terminal or n.io_schema.terminal_predicate is not None
        }

        # Iterative Tarjan SCC.
        index_counter = [0]
        stack: list[int] = []
        on_stack: set[int] = set()
        indices: dict[int, int] = {}
        lowlinks: dict[int, int] = {}
        sccs: list[list[int]] = []

        def _strongconnect(start: int) -> None:
            work = [(start, 0)]
            indices[start] = index_counter[0]
            lowlinks[start] = index_counter[0]
            index_counter[0] += 1
            stack.append(start)
            on_stack.add(start)
            while work:
                v, pi = work[-1]
                if pi < len(adj[v]):
                    w = adj[v][pi]
                    work[-1] = (v, pi + 1)
                    if w not in indices:
                        indices[w] = index_counter[0]
                        lowlinks[w] = index_counter[0]
                        index_counter[0] += 1
                        stack.append(w)
                        on_stack.add(w)
                        work.append((w, 0))
                    elif w in on_stack:
                        lowlinks[v] = min(lowlinks[v], indices[w])
                else:
                    if lowlinks[v] == indices[v]:
                        scc: list[int] = []
                        while True:
                            w = stack.pop()
                            on_stack.discard(w)
                            scc.append(w)
                            if w == v:
                                break
                        sccs.append(scc)
                    work.pop()

        for v in range(len(node_ids)):
            if v not in indices:
                _strongconnect(v)

        for scc in sccs:
            if len(scc) <= 1:
                continue
            if not (set(scc) & terminals):
                scc_names = sorted(node_ids[i] for i in scc)
                return PlanLiftError(
                    f"plan {plan_id!r}: strongly connected component "
                    f"{scc_names!r} contains no terminal node; the "
                    f"interpreter will loop inside the cycle indefinitely "
                    f"because no node's terminal_predicate will ever fire. "
                    f"Add a terminal node to the cycle, attach a "
                    f"terminal_predicate to one of its nodes, or "
                    f"restructure the edges.",
                    plan_id=plan_id,
                )
        return None


__all__ = ["CycleHasTerminalCheck"]
