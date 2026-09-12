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
from pathlib import Path
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
        binding = _binding_from_factory_or_binding(raw)
        # Legacy think/act yaml nests ``sub_spec_ref`` under ``config:``;
        # v2 puts it at the top level. Probe both surfaces so the
        # :class:`PlanNode.subgraph_ref` is populated regardless.
        config_raw = raw.get("config")
        sub_spec_raw = raw.get("sub_spec_ref")
        if sub_spec_raw is None and isinstance(config_raw, Mapping):
            sub_spec_raw = config_raw.get("sub_spec_ref")
        subgraph_ref = _subgraph_ref_from(sub_spec_raw)
        # When a node delegates to a subgraph, the inner entry's
        # io_schema is the SSOT for the outer port contract. The
        # outer kernel needs to read the right inputs from its
        # registry (e.g. ``decision`` for act.main) and write the
        # right outputs back, regardless of whether the outer yaml
        # uses ``inputs:`` or ``declared_inputs:`` on the node. Match
        # ``lift_executable_plan`` so v2 driver parity holds.
        schema = (
            _subgraph_entry_schema(subgraph_ref)
            if subgraph_ref is not None
            else _schema_from(raw.get("inputs"), raw.get("outputs"))
        )
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

    For nodes carrying a ``subgraph_ref``, the outer node's
    ``io_schema`` is derived from the inner entry node's declared
    ``io_schema``. This makes the subgraph delegate's port contract
    the single source of truth: the inner entry's ``inputs`` are
    forwarded from the outer registry by :class:`SubgraphStrategy`,
    and the inner entry's ``outputs`` are merged back. The outer
    node's ``io_schema`` cannot drift from the inner contract.
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
        io_schema = _subgraph_entry_schema(subgraph_ref)
        nodes.append(
            PlanNode(
                id=node_id,
                binding=binding,
                io_schema=io_schema,
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


def _subgraph_entry_schema(
    subgraph_ref: SubgraphReference | None,
) -> NodeIOSchema:
    """Return the inner entry node's :class:`NodeIOSchema` for a subgraph
    delegate, or an empty schema when no delegate is wired.

    Loading the inner plan is best-effort: tests and dry lifts may
    pass :class:`ExecutablePlan` shims whose ``plan_ref`` paths do
    not resolve. On failure, the outer node carries an empty schema
    (current behavior) so existing tests keep passing.
    """
    if subgraph_ref is None:
        return NodeIOSchema()
    try:
        import yaml

        path = _bundle_yaml_path(subgraph_ref.plan_ref)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return NodeIOSchema()
        spec = dict(raw)
        if "entry" not in spec and subgraph_ref.entry_node:
            spec["entry"] = subgraph_ref.entry_node
        inner_plan = lift_graph_spec(spec)
        return inner_plan.node(subgraph_ref.entry_node).io_schema
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return NodeIOSchema()


def _bundle_yaml_path(plan_ref: str) -> Path:
    """Resolve a bundle-relative ``plan_ref`` to a filesystem path.

    Mirrors ``subgraph_strategy._repo_root`` so the lifter can read
    inner plans at lift time without importing the strategy module
    (avoids a circular import).
    """
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file() and (parent / "bundles").is_dir():
            return parent / plan_ref
    return Path.cwd() / plan_ref


def _binding_from(value: object) -> BindingKind:
    if isinstance(value, BindingKind):
        return value
    if isinstance(value, str):
        try:
            return BindingKind(value)
        except ValueError:
            if value.startswith("concept."):
                return BindingKind.NODE_EXECUTOR
            raise ValueError(
                f"binding must be a BindingKind or string, got {value!r}"
            )
    raise ValueError(
        f"binding must be a BindingKind or string, got {type(value).__name__}"
    )


def _binding_from_factory_or_binding(raw: Mapping[str, object]) -> BindingKind:
    """Pick the right binding for a BundleGraphSpec-style node.

    Three inputs in priority order:

    1. ``binding:`` — explicit :class:`BindingKind` (v2 schema).
    2. ``sub_spec_ref:`` — nested subgraph; the kernel recurses via
       :class:`SubgraphStrategy`. Legacy think/act yaml nests
       ``sub_spec_ref:`` under ``config:`` (alongside ``max_visits``),
       so check both surfaces. Wins over ``factory`` so a node
       like ``think.reason`` (sub-spec only) recurses instead of
       dispatching a leaf executor that does not exist.
    3. ``factory:`` — legacy think/act subgraph style; ``factory:
       think.*`` / ``factory: act.*`` map to
       :class:`BindingKind.NODE_EXECUTOR` so the kernel can dispatch
       them via :class:`NodeExecutorStrategy`.
    """
    binding = raw.get("binding")
    if binding is not None:
        return _binding_from(binding)
    if raw.get("sub_spec_ref") is not None:
        return BindingKind.SUBGRAPH
    config = raw.get("config")
    if isinstance(config, Mapping) and config.get("sub_spec_ref") is not None:
        return BindingKind.SUBGRAPH
    factory = raw.get("factory")
    if factory is None:
        raise ValueError(
            "node spec must declare either 'binding' or 'factory'; "
            f"got neither in node keys={sorted(raw)}"
        )
    return BindingKind.NODE_EXECUTOR


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
    # Subgraph yaml often declares the same port as both input and output
    # (the node reads from upstream and writes its own decision). The
    # kernel treats inputs/outputs as one union for the strict-validator;
    # we deduplicate so the schema's "unique names" invariant holds.
    in_names = {p.name for p in in_specs}
    out_specs = tuple(p for p in out_specs if p.name not in in_names)
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
    # Legacy typed dataclass: ``PhaseNode.sub_spec_ref`` (ADR-0217 §3) is
    # a frozen dataclass with the same four fields as the new
    # ``SubgraphReference``. Read attributes directly.
    plan_ref = getattr(raw, "plan_ref", None)
    if plan_ref is None:
        return None
    return SubgraphReference(
        plan_ref=str(plan_ref),
        entry_node=str(getattr(raw, "entry_node", "") or ""),
        binding_edge=str(getattr(raw, "binding_edge", "") or ""),
        return_on=str(getattr(raw, "return_on", "next") or "next"),
    )


__all__ = ["lift_executable_plan", "lift_graph_spec"]
