"""PlanLifter — turns a yaml mapping (or an existing :class:`ExecutablePlan`)
into a :class:`Plan`.

The lifter is the single seam between the production bundle /
profile yaml and the new graph kernel. It accepts three input shapes:

- v1 entries-list shape (legacy think.yaml / act.yaml): the legacy
  ``lca.harness.declarative.compile.subgraph_resolver`` handles this.
- v2 pure-graph shape (``nodes`` / ``edges`` at the bundle root, per
  ADR-0217): this module's :func:`lift_graph_spec`.
- :class:`lca.harness.declarative.compile.assembler.assembler.ExecutablePlan`
  from the production interpreter: this module's :func:`lift_executable_plan`.

The lifter never instantiates a strategy or executor; it only
projects yaml / DTO into the new kernel's typed Plan DTO.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode, SubgraphReference


def lift_graph_spec(spec: Mapping[str, Any]) -> Plan:
    """Lift a v2 BundleGraphSpec-shaped mapping into a :class:`Plan`.

    Required keys: ``id``, ``nodes`` (sequence), `` ``edges`` (sequence).
    Optional: ``entry``, ``approval_resume_node``, ``declared_inputs``.
    Each node must carry ``id`` + ``binding`` (a :class:`BindingKind`
    value or its string); ``inputs``/``outputs`` are optional schema hints.
    """
    spec_id = str(spec.get("id", ""))
    raw_nodes = spec.get("nodes", ())
    raw_edges = spec.get("edges", ())
    raw_entry = spec.get("entry")
    if not isinstance(raw_nodes, (list, tuple)):
        raise ValueError(f"plan {spec_id!r}: nodes must be a sequence")
    nodes: list[PlanNode] = []
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise ValueError(f"plan {spec_id!r}: node must be a mapping")
        node_id = str(raw.get("id", "")).strip()
        if not node_id:
            raise ValueError(f"plan {spec_id!r}: node id must be non-empty")
        binding = _binding_from(raw.get("binding"))
        schema = _schema_from(raw.get("inputs"), raw.get("outputs"))
        subgraph_ref = _subgraph_ref_from(raw.get("sub_spec_ref"))
        nodes.append(
            PlanNode(
                id=node_id,
                binding=binding,
                io_schema=schema,
                config=dict(raw),
                max_visits=int(raw.get("max_visits", 1)),
                terminal=bool(raw.get("terminal", False)),
                entry=bool(raw.get("entry", False)) or raw_entry == node_id,
                subgraph_ref=subgraph_ref,
            )
        )
    edges: list[PlanEdge] = []
    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            continue
        source = str(raw.get("from") or raw.get("source", "")).strip()
        target = str(raw.get("to") or raw.get("target", "")).strip()
        if not source or not target:
            continue
        edges.append(
            PlanEdge(
                source=source,
                target=target,
                when=str(raw.get("when", "true")),
                subgraph_ref=_subgraph_ref_from(raw.get("subgraph_ref")),
            )
        )
    return Plan(
        id=spec_id,
        nodes=tuple(nodes),
        edges=tuple(edges),
        approval_resume_node=spec.get("approval_resume_node"),
    )


def lift_executable_plan(executable: object) -> Plan:
    """Lift a production :class:`ExecutablePlan` (or duck-typed equivalent)
    into the new :class:`Plan` shape.

    The legacy ``CognitivePhaseGraphPlan`` lives on ``executable.plan``.
    ``executable.plan.phase_graph`` (when present) is a phase graph;
    we project it. ``executable.nodes`` is the executable-node dict
    keyed by id; we use it for node ordering.
    """
    plan_obj = getattr(executable, "plan", None)
    pg = getattr(plan_obj, "phase_graph", None) if plan_obj is not None else None
    if pg is None:
        raise ValueError("ExecutablePlan has no phase_graph; cannot lift")
    raw_nodes = list(getattr(pg, "nodes", ()))
    raw_edges = list(getattr(pg, "edges", ()))
    entry_id = str(getattr(pg, "entry", ""))
    nodes: list[PlanNode] = []
    for raw in raw_nodes:
        binding = _binding_for_phase_node(raw)
        subgraph_ref = _subgraph_ref_from(getattr(raw, "sub_spec_ref", None))
        node_id = str(getattr(raw, "id", ""))
        nodes.append(
            PlanNode(
                id=node_id,
                binding=binding,
                max_visits=int(getattr(raw, "max_visits", 1)),
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
                when=str(getattr(raw, "when", "true")),
            )
        )
    return Plan(
        id=str(getattr(plan_obj, "id", "lifted")),
        nodes=tuple(nodes),
        edges=tuple(edges),
        approval_resume_node=getattr(pg, "approval_resume_node", None),
    )


def _binding_from(value: object) -> BindingKind:
    if isinstance(value, BindingKind):
        return value
    if isinstance(value, str):
        try:
            return BindingKind(value)
        except ValueError:
            # Legacy capability keys (e.g. "phase.perceive.standard",
            # "phase.think.standard") name PhaseExecutors. Default
            # anything phase.* to PHASE_EXECUTOR so legacy profiles
            # lift without modification. New yaml should use the
            # BindingKind value directly.
            if value.startswith("phase."):
                return BindingKind.PHASE_EXECUTOR
            if value.startswith("concept."):
                return BindingKind.NODE_EXECUTOR
            raise ValueError(
                f"binding must be a BindingKind or string, got {value!r}"
            )
    raise ValueError(
        f"binding must be a BindingKind or string, got {type(value).__name__}"
    )


def _binding_for_phase_node(raw: object) -> BindingKind:
    sub_ref = getattr(raw, "sub_spec_ref", None)
    binding_attr = getattr(raw, "binding", None)
    if sub_ref is not None:
        return BindingKind.SUBGRAPH
    if binding_attr is None:
        return BindingKind.TRANSFORM
    return _binding_from(binding_attr)


def _schema_from(inputs: object, outputs: object) -> NodeIOSchema:
    in_specs = _to_port_specs(inputs)
    out_specs = _to_port_specs(outputs)
    return NodeIOSchema(inputs=in_specs, outputs=out_specs)


def _to_port_specs(names: object) -> tuple[PortSpec, ...]:
    if names is None:
        return ()
    if isinstance(names, str):
        names = [names]
    if not isinstance(names, (list, tuple)):
        return ()
    out: list[PortSpec] = []
    for name in names:
        if not isinstance(name, str) or not name:
            continue
        try:
            out.append(PortSpec(name=name))
        except Exception:
            continue
    return tuple(out)


def _subgraph_ref_from(raw: object) -> SubgraphReference | None:
    if raw is None:
        return None
    if isinstance(raw, SubgraphReference):
        return raw
    if isinstance(raw, Mapping):
        return SubgraphReference(
            plan_ref=str(raw.get("plan_ref", "")),
            entry_node=str(raw.get("entry_node", "")),
            binding_edge=str(raw.get("binding_edge", "")),
            return_on=str(raw.get("return_on", "next")),
        )
    return None


__all__ = ["lift_executable_plan", "lift_graph_spec"]