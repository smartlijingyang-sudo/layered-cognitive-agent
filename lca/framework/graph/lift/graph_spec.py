"""v2 BundleGraphSpec → Plan lift (nodes/edges/entry).

Deep implementation behind :class:`~lca.framework.graph.lift.interface.PlanLifter`.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
from lca.framework.graph.lift.parsers import (
    binding_from_factory_or_binding,
    coerce_when,
    io_schema_from_mapping,
    schema_from,
    subgraph_ref_from,
)
from lca.framework.graph.lift.subgraph_contract import (
    enforce_subgraph_port_contract,
    require_subgraph_plan_exists,
    subgraph_entry_schema,
)
from lca.framework.graph.lift.validators import validate_predicates, validate_termination


def lift_graph_spec(spec: Mapping[str, Any]) -> Plan:
    """Lift a v2 BundleGraphSpec-shaped mapping into a :class:`Plan`.

    Runs predicate and termination validation after building the plan.
    See :func:`validate_predicates` and :func:`validate_termination`.
    """
    plan = lift_graph_spec_inner(spec)
    validate_predicates(plan)
    validate_termination(plan)
    return plan


def lift_graph_spec_inner(spec: Mapping[str, Any]) -> Plan:
    """Build a :class:`Plan` from a spec without validation.

    Used internally by :func:`lift_graph_spec` (which adds validation)
    and by :func:`subgraph_entry_schema` (which loads inner plans
    best-effort; running validation on incomplete inner plans would
    produce false positives).
    """
    spec_id = str(spec.get("id", ""))
    raw_nodes = spec.get("nodes", ())
    raw_edges = spec.get("edges", ())
    raw_entry = spec.get("entry")
    if raw_nodes is None:
        raw_nodes = ()
    if raw_edges is None:
        raw_edges = ()
    if not isinstance(raw_nodes, (list, tuple)):
        raise ValueError(f"plan {spec_id!r}: nodes must be a sequence")
    if not isinstance(raw_edges, (list, tuple)):
        raise ValueError(f"plan {spec_id!r}: edges must be a sequence")
    nodes: list[PlanNode] = []
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise ValueError(f"plan {spec_id!r}: node must be a mapping")
        node_id = str(raw.get("id", "")).strip()
        if not node_id:
            raise ValueError(f"plan {spec_id!r}: node id must be non-empty")
        binding = binding_from_factory_or_binding(raw)
        # Legacy think/act yaml nests ``sub_spec_ref`` under ``config:``;
        # v2 puts it at the top level. Probe both surfaces so the
        # :class:`PlanNode.subgraph_ref` is populated regardless.
        config_raw = raw.get("config")
        sub_spec_raw = raw.get("sub_spec_ref")
        if sub_spec_raw is None and isinstance(config_raw, Mapping):
            sub_spec_raw = config_raw.get("sub_spec_ref")
        subgraph_ref = subgraph_ref_from(sub_spec_raw)
        if subgraph_ref is not None and subgraph_ref.plan_ref:
            # The plan_ref must point to a real bundle file; a typo'd
            # or moved reference previously slipped through because
            # ``subgraph_entry_schema`` silently swallows load errors
            # and returns an empty schema, so the outer node lifted
            # clean and the kernel crashed at first dispatch. Lift-time
            # check turns this into a fail-loud error.
            require_subgraph_plan_exists(spec_id, node_id, subgraph_ref)
        # First-principle port-naming for subgraph nodes: the YAML's
        # ``declared_inputs``/``declared_outputs`` are the **outer-facing**
        # port names (what the outer kernel reads from / writes to its
        # port registry). The inner subgraph entry's ``inputs``/``outputs``
        # are the **inner-facing** port names. They can legitimately
        # differ — e.g. ``phase_main_outer.yaml::reflect.main`` declares
        # ``declared_inputs: [act_outcome]`` while the inner subgraph
        # reads ``observation``. Carrying both schemas lets the kernel
        # read ``act_outcome`` from its own registry and have
        # :class:`SubgraphStrategy` translate the value across the seam
        # into ``observation`` for the inner. When the YAML omits
        # ``declared_inputs``/``declared_outputs`` we fall back to the
        # inner entry's schema (legacy behavior — port names coincide).
        schema: NodeIOSchema
        inner_schema: NodeIOSchema | None = None
        if subgraph_ref is not None:
            inner_schema = subgraph_entry_schema(subgraph_ref)
            declared_in = raw.get("declared_inputs")
            declared_out = raw.get("declared_outputs")
            if declared_in is not None or declared_out is not None:
                schema = schema_from(declared_in, declared_out)
                # Subgraph port contract (ADR-0217 §3.3.3 +
                # first-principle port-naming): outer-facing declared
                # port names must exist in the inner plan's reachable
                # port set, otherwise the kernel silently reads None /
                # drops values at runtime. Catch the mismatch at lift
                # time so a mis-wired bundle fails boot instead of
                # leaking a missing-port crash at first dispatch.
                enforce_subgraph_port_contract(
                    spec_id=spec_id,
                    node_id=node_id,
                    outer_schema=schema,
                    subgraph_ref=subgraph_ref,
                    declared_inputs_present=declared_in is not None,
                    declared_outputs_present=declared_out is not None,
                )
            else:
                schema = inner_schema
        else:
            # BundleGraphSpec uses flat ``inputs``/``outputs``; the Plan SDK
            # serialize shape nests them under ``io_schema`` (with optional
            # ``terminal_predicate``). Accept both so plan_sdk can talk only
            # to the Lift interface for YAML → Plan.
            nested = raw.get("io_schema")
            if isinstance(nested, Mapping):
                schema = io_schema_from_mapping(nested)
            else:
                schema = schema_from(raw.get("inputs"), raw.get("outputs"))
        nodes.append(
            PlanNode(
                id=node_id,
                binding=binding,
                io_schema=schema,
                inner_io_schema=inner_schema if subgraph_ref is not None else None,
                config=dict(raw),
                terminal=bool(raw.get("terminal", False)),
                entry=bool(raw.get("entry", False)) or raw_entry == node_id,
                subgraph_ref=subgraph_ref,
            )
        )
    edges: list[PlanEdge] = []
    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            raise PlanLiftError(
                f"plan {spec_id!r}: edge must be a mapping, got {type(raw).__name__}"
            )
        source = str(raw.get("from") or raw.get("source", "")).strip()
        target = str(raw.get("to") or raw.get("target", "")).strip()
        if not source:
            raise PlanLiftError(
                f"plan {spec_id!r}: edge missing 'from' (or 'source'): {dict(raw)}"
            )
        if not target:
            raise PlanLiftError(
                f"plan {spec_id!r}: edge missing 'to' (or 'target'): {dict(raw)}"
            )
        edges.append(
            PlanEdge(
                source=source,
                target=target,
                when=coerce_when(raw.get("when")),
                subgraph_ref=subgraph_ref_from(raw.get("subgraph_ref")),
            )
        )
    return Plan(
        id=spec_id,
        nodes=tuple(nodes),
        edges=tuple(edges),
        approval_resume_node=spec.get("approval_resume_node"),
    )


# Backward-compatible private alias.
_lift_graph_spec_inner = lift_graph_spec_inner

__all__ = ["_lift_graph_spec_inner", "lift_graph_spec", "lift_graph_spec_inner"]
