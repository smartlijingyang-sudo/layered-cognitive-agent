"""``max_visits`` vs SCC size — runtime budget collision detector.

A typed-port graph with a strongly connected component (SCC) of
size ``k`` can re-enter a node up to ``max_visits`` times *across
the cycle*. If a node carries ``max_visits < k``, the interpreter
burns through the budget on cycle entry and exits with
``budget_exceeded`` before the cycle reaches its natural terminal —
producing ``session_status=failed`` with no observable error
surface for the operator.

This check computes the SCC partition once and verifies
``max_visits(node) >= size(node_scc)`` for every node. Tests use
the same iterative Tarjan algorithm as the cycle_terminal check;
copying is intentional so each check is independently testable.

Skip subgraph delegate nodes — their cycle behaviour is bound to
the outer caller's ``binding_edge``, not to an in-plan SCC.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class MaxVisitsVsSccCheck(PlanCheck):
    """Reject ``max_visits`` smaller than the node's SCC size.

    Static reachability of a terminal elsewhere in the plan is
    not enough — a cycle that doesn't include a terminal leaves
    the kernel trapped inside it on every entry. Pair with
    :class:`CycleHasTerminalCheck` for the "every cycle includes
    a terminal" half; this check covers "the cycle has enough
    budget to converge" the other half.
    """

    check_id = "max_visits_vs_scc"
    label = "max_visits >= SCC size (no budget collision)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        node_ids = [n.id for n in plan.nodes]
        if not node_ids:
            return None
        index_of = {nid: i for i, nid in enumerate(node_ids)}
        adj: list[list[int]] = [[] for _ in node_ids]
        for edge in plan.edges:
            if edge.source in index_of and edge.target in index_of:
                adj[index_of[edge.source]].append(index_of[edge.target])

        scc_of: list[int] = [-1] * len(node_ids)
        scc_index_counter = [0]
        scc_stack: list[int] = []
        scc_on_stack: set[int] = set()
        scc_indices: dict[int, int] = {}
        scc_lowlinks: dict[int, int] = {}

        def _run_scc(start: int) -> None:
            work = [(start, 0)]
            scc_indices[start] = scc_index_counter[0]
            scc_lowlinks[start] = scc_index_counter[0]
            scc_index_counter[0] += 1
            scc_stack.append(start)
            scc_on_stack.add(start)
            while work:
                v, pi = work[-1]
                if pi < len(adj[v]):
                    w = adj[v][pi]
                    work[-1] = (v, pi + 1)
                    if w not in scc_indices:
                        scc_indices[w] = scc_index_counter[0]
                        scc_lowlinks[w] = scc_index_counter[0]
                        scc_index_counter[0] += 1
                        scc_stack.append(w)
                        scc_on_stack.add(w)
                        work.append((w, 0))
                    elif w in scc_on_stack:
                        scc_lowlinks[v] = min(scc_lowlinks[v], scc_indices[w])
                else:
                    if scc_lowlinks[v] == scc_indices[v]:
                        comp: list[int] = []
                        while True:
                            w = scc_stack.pop()
                            scc_on_stack.discard(w)
                            comp.append(w)
                            if w == v:
                                break
                        comp_id = comp[0]
                        for w in comp:
                            scc_of[w] = comp_id
                    # Pop ``v`` from the work stack first, then
                    # back-propagate its lowlink to the parent (the
                    # classical recursive Tarjan does this on the
                    # return — the iterative form has to do it
                    # explicitly). The order matters: after the pop
                    # ``work[-1][0]`` is the parent, not the node we
                    # just finished.
                    work.pop()
                    if work:
                        parent = work[-1][0]
                        scc_lowlinks[parent] = min(
                            scc_lowlinks[parent], scc_lowlinks[v]
                        )

        for v in range(len(node_ids)):
            if scc_indices.get(v) is None:
                _run_scc(v)

        scc_size: dict[int, int] = {}
        for comp_id in set(scc_of):
            scc_size[comp_id] = sum(1 for x in scc_of if x == comp_id)

        for node in plan.nodes:
            comp_id = scc_of[index_of[node.id]]
            required = scc_size[comp_id]
            if node.max_visits < required:
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} max_visits="
                    f"{node.max_visits} but it lives in a "
                    f"strongly connected component of size "
                    f"{required}; the interpreter will hit "
                    f"budget_exceeded before the cycle converges "
                    f"and exit with ``session_status=failed``. "
                    f"Raise ``max_visits`` to at least {required} or "
                    f"break the cycle with a one-way exit edge.",
                    plan_id=plan_id,
                    node_id=node.id,
                )
        return None


__all__ = ["MaxVisitsVsSccCheck"]
