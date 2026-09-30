"""Typed-port wiring check for boot-time plan validation.

Reject edges whose target expects a port no predecessor produces.

The lifter validates single-edge predicate ports (:mod:`lifter`'s
:func:`validate_predicates`) but does not run a typed-port
reachability check across the plan — :class:`NodeIOSchema.required_inputs`
is satisfied lazily by :class:`PortRegistry` at runtime, so a
typo'd required port only blows up when the executor actually
walks that node. This check computes the predecessor output set
per node and rejects every missing-port case at boot time.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan


def _check_typed_port_wiring(plan: Plan, *, plan_id: str) -> PlanLiftError | None:
    """Reject edges whose target expects a port no predecessor produces.

    The lifter validates single-edge predicate ports (:mod:`lifter`'s
    :func:`validate_predicates`) but does not run a typed-port
    reachability check across the plan — :class:`NodeIOSchema.required_inputs`
    is satisfied lazily by :class:`PortRegistry` at runtime, so a
    typo'd required port only blows up when the executor actually
    walks that node. This check computes the predecessor output set
    per node and rejects every missing-port case at boot time.

    Entry-node inputs are out of scope: the entry's inputs are
    supplied by the **outer caller** (parent plan via
    :class:`SubgraphStrategy` forwarding, or the top-level kernel).
    Computing "available" for an entry node would require caller-side
    context that the boot-time validator doesn't have.

    Subgraph delegate nodes (``subgraph_ref`` wired) are also
    out of scope: their inputs are forwarded by the surrounding
    caller via :class:`SubgraphStrategy`, not by an in-plan
    predecessor. The kernel reads them from the registry when the
    subgraph is entered, so a missing predecessor in the
    enclosing plan does not indicate a real wiring fault.
    """
    skip_ids = {n.id for n in plan.nodes if n.entry or n.subgraph_ref is not None}
    output_produced: dict[str, frozenset[str]] = {
        n.id: n.io_schema.output_names() for n in plan.nodes
    }
    predecessors: dict[str, frozenset[str]] = {n.id: frozenset() for n in plan.nodes}
    for edge in plan.edges:
        predecessors[edge.target] = predecessors.get(edge.target, frozenset()) | {edge.source}
    # Every node starts with its own declared outputs (these are
    # what it *emits*); fixed-point propagation then augments
    # ``available`` with the union of every predecessor's available
    # set, so a node's ``available`` is the union of "what I emit"
    # and "what flows in from reachable predecessors". Entry nodes
    # also start with their own outputs so a downstream node that
    # targets the entry as its predecessor (common in subgraph
    # delegates, where the entry is the delegate's entry) still
    # gets the right "available" set.
    available: dict[str, frozenset[str]] = {n.id: output_produced[n.id] for n in plan.nodes}
    changed = True
    while changed:
        changed = False
        for node_id, preds in predecessors.items():
            if not preds:
                continue
            merged: set[str] = set(available[node_id])
            for p in preds:
                merged |= available.get(p, frozenset())
            new = frozenset(merged)
            if new != available[node_id]:
                available[node_id] = new
                changed = True
    for node in plan.nodes:
        if node.id in skip_ids:
            continue
        required = node.io_schema.required_inputs()
        if not required:
            continue
        missing = [p for p in required if p not in available[node.id]]
        if not missing:
            continue
        return PlanLiftError(
            f"plan {plan_id!r}: node {node.id!r} required inputs "
            f"{missing!r} are not produced by any reachable predecessor "
            f"(available={sorted(available[node.id])}; "
            f"predecessors={sorted(predecessors[node.id])})",
            plan_id=plan_id,
            node_id=node.id,
        )
    return None


__all__ = ["_check_typed_port_wiring"]
