"""Reachability / termination / cycle checks for lifted plans.

These free-function checks are the original boot-time graph
invariants, kept for backward compat with the tests that import them
by name. Class-based equivalents live in the ``checks/`` subpackage
(:class:`~lca_kernel.boot.plan_validation.checks.reachability.ReachabilityCheck`
and friends); :data:`lca_kernel.boot.plan_validation.core._PLAN_CHECKS`
wires the free functions for the outer plan.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan


def _check_reachability(plan: Plan, *, plan_id: str) -> PlanLiftError | None:
    """Reject nodes that the entry cannot reach via the edge graph.

    A plan with disconnected subgraphs would silently skip those
    subgraphs at runtime — they exist in :class:`Plan.nodes` but
    no edge sequence ever visits them. Lift-time reachability
    catches this so a typo'd edge target or an accidentally
    orphaned node fails boot instead of being dead code.
    """
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


def _check_terminal_reachable_from_entry(plan: Plan, *, plan_id: str) -> PlanLiftError | None:
    """Reject plans where no terminal node is reachable from the entry.

    The kernel terminates when it visits a node with
    ``terminal=True`` (or when a node's ``terminal_predicate``
    fires). If the BFS from the plan entry never reaches such a
    node the kernel runs forever (the classic "infinite loop"
    graph bug — see e.g. Cordis / react-flow / igraph stack
    traces). Catch the unreachable-termination case at boot time.
    """
    entry_id = next((n.id for n in plan.nodes if n.entry), None)
    if entry_id is None:
        return None
    terminals = {
        n.id for n in plan.nodes if n.terminal or n.io_schema.terminal_predicate is not None
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


def _check_terminal_no_outgoing_edges(plan: Plan, *, plan_id: str) -> PlanLiftError | None:
    """Reject ``terminal=True`` nodes with outgoing edges.

    A terminal node is meant to be a sink — once the kernel visits
    it the plan completes. Outgoing edges from a terminal node are
    dead code (the kernel never traverses them) and confuse the
    static graph view (operators see a "transition" that never
    fires). Subgraph delegate nodes are exempt because their
    binding_edge re-enters the outer caller, not a downstream
    node in the same plan.
    """
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


def _check_cycle_has_terminal(plan: Plan, *, plan_id: str) -> PlanLiftError | None:
    """Reject cycles that contain no terminal node.

    A strongly connected component without a terminal node is a
    classic "infinite loop" trap — the interpreter enters the
    cycle and has no termination signal inside it. Static
    reachability of a terminal elsewhere in the plan is not
    enough: a cycle that doesn't include a terminal leaves the
    kernel trapped inside it on every entry. The check
    complements :func:`_check_terminal_reachable_from_entry` —
    reachability asks "is a terminal reachable from entry", this
    check asks "does every cycle pass through a terminal".
    """
    # Tarjan-style SCC over the plan graph.
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
    # Iterative Tarjan to avoid recursion limits on large graphs.
    index_counter = [0]
    stack: list[int] = []
    on_stack: set[int] = set()
    indices: dict[int, int] = {}
    lowlinks: dict[int, int] = {}
    sccs: list[list[int]] = []

    def strongconnect(start: int) -> None:
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
            strongconnect(v)
    for scc in sccs:
        if len(scc) <= 1:
            # Single-node SCC: a non-self-loop single-node SCC
            # trivially terminates; self-loops are protected by
            # terminal_predicate (PR2) or the kernel's
            # AgentState.budget.
            continue
        if not (set(scc) & terminals):
            scc_names = sorted(node_ids[i] for i in scc)
            return PlanLiftError(
                f"plan {plan_id!r}: strongly connected component "
                f"{scc_names!r} contains no terminal node; the "
                f"interpreter will loop inside the cycle. Add a "
                f"terminal node to the cycle or break the cycle "
                f"with a one-way exit edge.",
                plan_id=plan_id,
            )
    return None


__all__ = [
    "_check_cycle_has_terminal",
    "_check_reachability",
    "_check_terminal_no_outgoing_edges",
    "_check_terminal_reachable_from_entry",
]
