"""ExecutablePlan / duck-typed production DTO → Plan lift.

Deep implementation behind :class:`~lca.framework.graph.lift.interface.PlanLifter`.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.framework.graph.lift.parsers import (
    binding_for_phase_node,
    coerce_loop,
    coerce_when,
    subgraph_ref_from,
)
from lca.framework.graph.lift.subgraph_contract import subgraph_entry_schema


def lift_executable_plan(executable: object) -> Plan:
    """Lift a production :class:`ExecutablePlan` (or duck-typed equivalent)
    into the new :class:`Plan` shape.

    Pass-through: if ``executable`` is already a v2 :class:`Plan`
    (kernel-native ``lift_graph_spec`` result), return it unchanged.
    The v2 driver in :mod:`lca.loop.driver` constructs the ``Plan``
    directly and hands it to ``interpreter.run`` without an
    ``ExecutablePlan`` wrapper.

    The legacy ``CognitivePhaseGraphPlan`` lives on ``executable.plan``.
    ``executable.plan.phase_graph`` (when present) is a phase graph;
    we project it. ``executable.nodes`` is the executable-node dict
    keyed by id; we use it for node ordering.

    For nodes carrying a ``subgraph_ref``, the outer node's
    ``io_schema`` is derived from the inner entry node's declared
    ``io_schema``. This makes the subgraph delegate's port contract
    the single source of truth: the inner entry's ``inputs`` are
    forwarded from the outer registry by :class:`SubgraphStrategy`,
    and the inner entry's ``outputs`` are merged back. The outer
    node's ``io_schema`` cannot drift from the inner contract.
    """
    if isinstance(executable, Plan):
        return executable
    plan_obj = getattr(executable, "plan", None)
    pg = getattr(plan_obj, "phase_graph", None) if plan_obj is not None else None
    if pg is None:
        raise ValueError("ExecutablePlan has no phase_graph; cannot lift")
    raw_nodes = list(getattr(pg, "nodes", ()))
    raw_edges = list(getattr(pg, "edges", ()))
    entry_id = str(getattr(pg, "entry", ""))
    nodes: list[PlanNode] = []
    for raw in raw_nodes:
        binding = binding_for_phase_node(raw)
        subgraph_ref = subgraph_ref_from(getattr(raw, "sub_spec_ref", None))
        node_id = str(getattr(raw, "id", ""))
        io_schema = subgraph_entry_schema(subgraph_ref)
        # Legacy path has no declared_inputs/declared_outputs; outer
        # and inner port names coincide, so ``inner_io_schema`` equals
        # ``io_schema`` (identity translation at the subgraph seam).
        nodes.append(
            PlanNode(
                id=node_id,
                binding=binding,
                io_schema=io_schema,
                inner_io_schema=io_schema if subgraph_ref is not None else None,
                terminal=bool(getattr(raw, "terminal", False)),
                entry=bool(getattr(raw, "entry", False)) or node_id == entry_id,
                subgraph_ref=subgraph_ref,
            )
        )
    edges: list[PlanEdge] = []
    for raw in raw_edges:
        edges.append(
            PlanEdge(
                source=str(getattr(raw, "source", "")),
                target=str(getattr(raw, "target", "")),
                when=coerce_when(getattr(raw, "when", "true")),
                loop=coerce_loop(getattr(raw, "loop", None)),
            )
        )
    return Plan(
        id=str(getattr(plan_obj, "id", "lifted")),
        nodes=tuple(nodes),
        edges=tuple(edges),
        approval_resume_node=getattr(pg, "approval_resume_node", None),
    )


__all__ = ["lift_executable_plan"]
