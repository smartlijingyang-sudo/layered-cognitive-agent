"""Unused (dead) output port check.

Reject nodes that declare an output port no reachable successor
requires. Such a port is dead code at runtime — the kernel hands
the value to :class:`PortRegistry` but no downstream node reads
it, so a typo'd port name (e.g. ``score_v2`` instead of ``score``)
or a port left over from a deleted edge stays silent until a
human reads the plan.

The complement (required input never produced by a predecessor)
is caught by :class:`TypedPortWiringCheck` — this check focuses
on the **producer** side.

Skip:

- **Subgraph delegate nodes** — their outputs are forwarded to
  the outer caller by :class:`SubgraphStrategy`, not consumed by
  an in-plan successor. Marking them "all consumed" keeps the
  check from false-positives on the inner-to-outer boundary.
- **Terminal nodes** — their outputs are consumed by the kernel
  as the termination signal, not by any successor node. The
  :attr:`PlanNode.terminal_predicate` path reads them.
- **Entry nodes** — their inputs come from the outer caller
  (parent plan or kernel), not from an in-plan predecessor. The
  dual concern (entry's outputs being consumed outside the plan)
  is the same shape as subgraph delegates, so entry is treated
  symmetrically.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

from .base import PlanCheck


class UnusedPortsCheck(PlanCheck):
    """Plan-level unused port check: declared outputs must be consumed by
    some reachable successor in the same plan.

    BFS-reachable successor closure is computed once per node; the
    union of ``required_inputs()`` across the closure tells us
    which ports the node's downstream actually reads. Any declared
    output missing from that union is dead code.
    """

    check_id = "unused_ports"
    label = "All declared ports are consumed (no dead code)"

    def run(self, plan: Plan, *, plan_id: str) -> PlanLiftError | None:
        # Inner subgraph plans forward their output to the outer
        # caller via :class:`SubgraphStrategy` — an inner node's
        # output doesn't need an in-plan successor to be useful.
        # The check is wired in :func:`validate_profile_plans` to
        # run only on outer plans (the caller passes ``_is_outer``
        # as a sentinel via the ``plan_id`` prefix; we don't have
        # the flag here, so we skip if any node carries a
        # ``subgraph_ref`` — that marks the plan as an outer plan
        # with phase subgraph delegates).
        if any(n.subgraph_ref is not None for n in plan.nodes):
            return None
        skip_ids: set[str] = {
            n.id for n in plan.nodes if n.entry or n.terminal or n.subgraph_ref is not None
        }
        successors: dict[str, set[str]] = {n.id: set() for n in plan.nodes}
        for edge in plan.edges:
            successors[edge.source].add(edge.target)

        # Transitive successor closure per node, skipping the
        # boundary kinds (entry / terminal / subgraph delegate)
        # so the BFS doesn't walk into them.
        transitive_succs: dict[str, frozenset[str]] = {n.id: frozenset() for n in plan.nodes}
        for n in plan.nodes:
            if n.id in skip_ids:
                continue
            visited: set[str] = set()
            stack: list[str] = list(successors[n.id])
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                stack.extend(successors[cur])
            transitive_succs[n.id] = frozenset(visited)

        for node in plan.nodes:
            if node.id in skip_ids:
                continue
            if not node.io_schema.outputs:
                continue
            required_by_succs: set[str] = set()
            for succ_id in transitive_succs[node.id]:
                succ_node = _node_by_id(plan, succ_id)
                if succ_node is None:
                    continue
                required_by_succs.update(succ_node.io_schema.required_inputs())
            for out_port in node.io_schema.output_names():
                if out_port in required_by_succs:
                    continue
                return PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} declares output "
                    f"port {out_port!r} but no reachable successor "
                    f"requires it (dead output). Either remove the "
                    f"declaration, or wire it into a downstream "
                    f"node's required inputs.",
                    plan_id=plan_id,
                    node_id=node.id,
                    port_name=out_port,
                )
        return None


def _node_by_id(plan: Plan, node_id: str):  # type: ignore[no-untyped-def]
    for n in plan.nodes:
        if n.id == node_id:
            return n
    return None


__all__ = ["UnusedPortsCheck"]
