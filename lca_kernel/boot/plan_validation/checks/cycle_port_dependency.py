"""Cycle port dependency check.

Reject strongly connected components (SCCs) whose nodes form a
**port-level mutual dependency** — node A requires a port produced
only by node B, and node B requires a port produced only by node A.
In a typed-port runtime this is a deadlock: A cannot fire until B
produces its required port, and B cannot fire until A produces its
required port. No node ever satisfies its schema's
``required_inputs()``, so the plan cannot make progress.

Why this is a static check, not a runtime one
----------------------------------------------

The runtime cannot detect this because:

- :class:`PlanLifter` accepts plans whose per-node schemas are
  individually satisfied by the union of upstream outputs (the
  cycle as a whole satisfies the schema — see Case 5 below for a
  counter-example).
- The interpreter enters the cycle and immediately blocks on the
  first missing port, with no static signal that the dependency
  edge inside the SCC is reciprocal rather than sequential.

The check is intentionally local to each SCC: if the dependency
graph within an SCC has any 2-cycle on port edges, fail. A linear
chain ``A→B→C`` is fine because each port is produced by an
earlier node and consumed by a later one; a 3-node cycle where the
dependency relation forms a directed cycle ``A→B→C→A`` is a
scheduling bug but it is not a mutual-dependency deadlock (the
runtime can still resolve the cycle via ``max_visits`` /
``terminal_predicate`` — see :class:`CycleHasTerminalCheck`). Only
the *mutual* port dependency pair is fatal because every node
needs a port that its only potential producer also needs.

Single-node SCCs are skipped — self-loop port dependencies are a
narrower concern covered by :class:`SelfLoopSafeCheck`.
Subgraph delegate nodes (``subgraph_ref is not None``) are also
skipped because their IO schema is delegated to the inner plan and
the outer kernel cannot reason about port resolution statically.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class CyclePortDependencyCheck(PlanCheck):
    """Reject SCCs whose nodes form a mutual port-level dependency."""

    check_id = "cycle_port_dependency"
    label = "Cycle port dependency (no runtime deadlock)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        """Return a :class:`PlanLiftError` if any SCC has a port-level 2-cycle.

        Algorithm:

        1. Build the adjacency list from ``plan.edges`` and compute SCCs
           using an iterative Tarjan pass (mirrors
           :class:`CycleHasTerminalCheck` but kept independent so this
           check file is self-contained and unit-testable).
        2. For every SCC of size ``>= 2``, check every ordered pair of
           distinct nodes ``(n_a, n_b)``: does ``n_a`` require any port
           that ``n_b`` produces, AND does ``n_b`` require any port that
           ``n_a`` produces? If yes, the pair is mutually blocking.
        3. Skip subgraph delegates — their IO schema is opaque to the
           outer kernel and the inner subgraph resolves port edges
           against its own plan.
        """
        node_ids = [n.id for n in plan.nodes]
        if not node_ids:
            return None

        index_of = {nid: i for i, nid in enumerate(node_ids)}
        adj: list[list[int]] = [[] for _ in node_ids]
        for edge in plan.edges:
            if edge.source in index_of and edge.target in index_of:
                adj[index_of[edge.source]].append(index_of[edge.target])

        # Iterative Tarjan SCC. Copied from cycle_terminal.py — kept
        # independent so each check file is self-contained.
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
            if len(scc) < 2:
                continue
            for i_idx in range(len(scc)):
                for j_idx in range(len(scc)):
                    if i_idx == j_idx:
                        continue
                    i = scc[i_idx]
                    j = scc[j_idx]
                    n_i = plan.nodes[i]
                    n_j = plan.nodes[j]
                    # Subgraph delegates resolve ports inside their
                    # inner plan — the outer kernel has no static
                    # view of port satisfaction, so skip them.
                    if n_i.subgraph_ref is not None or n_j.subgraph_ref is not None:
                        continue
                    j_outputs = n_j.io_schema.output_names()
                    i_outputs = n_i.io_schema.output_names()
                    i_needs_from_j = {
                        p for p in n_i.io_schema.required_inputs() if p in j_outputs
                    }
                    j_needs_from_i = {
                        p for p in n_j.io_schema.required_inputs() if p in i_outputs
                    }
                    if i_needs_from_j and j_needs_from_i:
                        return PlanLiftError(
                            f"plan {plan_id!r}: SCC has port-level mutual "
                            f"dependency: node {n_i.id!r} requires "
                            f"{sorted(i_needs_from_j)!r} from {n_j.id!r} "
                            f"AND node {n_j.id!r} requires "
                            f"{sorted(j_needs_from_i)!r} from {n_i.id!r}. "
                            f"This forms a runtime deadlock: neither node "
                            f"can produce its required port without the "
                            f"other producing first.",
                            plan_id=plan_id,
                            node_id=n_i.id,
                        )
        return None


__all__ = ["CyclePortDependencyCheck"]
