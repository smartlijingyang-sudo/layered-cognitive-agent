"""PlanLifter — turns a yaml mapping (or an existing :class:`ExecutablePlan`)
into a :class:`Plan`.

The lifter is the single seam between the production bundle /
profile yaml and the new graph kernel. It accepts three input shapes:

- v1 entries-list shape (legacy think.yaml / act.yaml): the legacy
  ``lca.harness.declarative.compile.subgraph_resolver`` handles this.
- v2 pure-graph shape (``nodes`` / ``edges`` at the bundle root, per
  ADR-0217): this module's :func:`lift_graph_spec`.
- the retired v0 ExecutablePlan (deleted ADR-0221 P3)
  from the production interpreter: this module's :func:`lift_executable_plan`.

The lifter never instantiates a strategy or executor; it only
projects yaml / DTO into the new kernel's typed Plan DTO.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode, SubgraphReference
from lca.contracts.protocols.graph.predicate import PortRef, Predicate


def lift_graph_spec(spec: Mapping[str, Any]) -> Plan:
    """Lift a v2 BundleGraphSpec-shaped mapping into a :class:`Plan`.

    Runs predicate, termination, and approval-resume-node validation
    after building the plan. See :func:`validate_predicates`,
    :func:`_validate_termination`, and
    :func:`_validate_approval_resume_node`.
    """
    plan = _lift_graph_spec_inner(spec)
    validate_predicates(plan)
    _validate_termination(plan)
    _validate_approval_resume_node(plan)
    return plan


def _validate_approval_resume_node(plan: Plan) -> None:
    """Fail-loud when ``act.approve.gate`` is declared without a resume edge.

    PR-1 (closes 评审 §6.1 + G-1 hot path): HITL without a resume edge
    is unsafe — the interrupt can pause a run but never recover, so
    the next user command is dropped on the floor. This check fires
    at every ``lift_graph_spec`` call (including the boot-time
    ``validate_profile_plans`` walk) so the operator sees the
    failure before the first run.

    The check is per-plan: any plan that declares ``act.approve.gate``
    as one of its nodes must also declare a cross-subgraph
    ``intervene.resume → act.approve.gate`` edge in the same plan.
    Plans without the gate are unaffected (gated on
    ``act.approve.gate in node_ids``).

    Per-plan (not cross-plan) is intentional: the validator walks
    every bundle in :func:`validate_profile_plans` independently, so
    a single per-plan rule keeps the check local and predictable.
    The outer plan's ``act.approve.gate`` delegate is checked here
    (the outer delegate needs the resume edge as much as the inner
    gate does); the inner ``act.subgraph`` plan's gate has its own
    resume edge added in :file:`bundles/act/act_subgraph.yaml`.
    """
    node_ids = {n.id for n in plan.nodes}
    if "act.approve.gate" not in node_ids:
        return
    resume_edge_present = any(
        e.source == "intervene.resume" and e.target == "act.approve.gate" for e in plan.edges
    )
    if resume_edge_present:
        return
    raise PlanLiftError(
        "act.approve.gate is declared but the cross-subgraph resume edge "
        "``intervene.resume → act.approve.gate`` is missing — HITL without "
        "a resume edge is unsafe (the interrupt can pause a run but never "
        "recover; subsequent user commands are dropped). Add the resume "
        "edge in this plan or remove the gate declaration.",
        plan_id=plan.id,
        node_id="act.approve.gate",
        next_command="./scripts/lca-ops plan validate bundles/outer/phase_main.yaml",
    )


def _lift_graph_spec_inner(spec: Mapping[str, Any]) -> Plan:
    """Build a :class:`Plan` from a spec without validation.

    Used internally by :func:`lift_graph_spec` (which adds validation)
    and by :func:`_subgraph_entry_schema` (which loads inner plans
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
        binding = _binding_from_factory_or_binding(raw)
        # Legacy think/act yaml nests ``sub_spec_ref`` under ``config:``;
        # v2 puts it at the top level. Probe both surfaces so the
        # :class:`PlanNode.subgraph_ref` is populated regardless.
        config_raw = raw.get("config")
        sub_spec_raw = raw.get("sub_spec_ref")
        if sub_spec_raw is None and isinstance(config_raw, Mapping):
            sub_spec_raw = config_raw.get("sub_spec_ref")
        subgraph_ref = _subgraph_ref_from(sub_spec_raw)
        if subgraph_ref is not None and subgraph_ref.plan_ref:
            # The plan_ref must point to a real bundle file; a typo'd
            # or moved reference previously slipped through because
            # ``_subgraph_entry_schema`` silently swallows load errors
            # and returns an empty schema, so the outer node lifted
            # clean and the kernel crashed at first dispatch. Lift-time
            # check turns this into a fail-loud error.
            _require_subgraph_plan_exists(spec_id, node_id, subgraph_ref)
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
            inner_schema = _subgraph_entry_schema(subgraph_ref)
            declared_in = raw.get("declared_inputs")
            declared_out = raw.get("declared_outputs")
            if declared_in is not None or declared_out is not None:
                schema = _schema_from(declared_in, declared_out)
                # Subgraph port contract (ADR-0217 §3.3.3 +
                # first-principle port-naming): outer-facing declared
                # port names must exist in the inner plan's reachable
                # port set, otherwise the kernel silently reads None /
                # drops values at runtime. Catch the mismatch at lift
                # time so a mis-wired bundle fails boot instead of
                # leaking a missing-port crash at first dispatch.
                _enforce_subgraph_port_contract(
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
            schema = _schema_from(raw.get("inputs"), raw.get("outputs"))
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
            raise PlanLiftError(f"plan {spec_id!r}: edge missing 'from' (or 'source'): {dict(raw)}")
        if not target:
            raise PlanLiftError(f"plan {spec_id!r}: edge missing 'to' (or 'target'): {dict(raw)}")
        edges.append(
            PlanEdge(
                source=source,
                target=target,
                when=_coerce_when(raw.get("when")),
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
        binding = _binding_for_phase_node(raw)
        subgraph_ref = _subgraph_ref_from(getattr(raw, "sub_spec_ref", None))
        node_id = str(getattr(raw, "id", ""))
        io_schema = _subgraph_entry_schema(subgraph_ref)
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
                when=_coerce_when(getattr(raw, "when", "true")),
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
        inner_plan = _lift_graph_spec_inner(spec)
        return inner_plan.node(subgraph_ref.entry_node).io_schema
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return NodeIOSchema()


def _require_subgraph_plan_exists(
    spec_id: str, node_id: str, subgraph_ref: SubgraphReference
) -> None:
    """Raise :class:`PlanLiftError` if *subgraph_ref.plan_ref* points nowhere.

    Subgraph delegates whose target file is missing or unreadable
    silently degrade today (``_subgraph_entry_schema`` returns an
    empty schema on load failure, leaving the outer node with no
    inputs / no outputs and the kernel crashing at first dispatch).
    Catching this at lift time surfaces a structured boot error so
    the operator sees the wrong ``plan_ref`` next to the wrong node.
    """
    try:
        path = _bundle_yaml_path(subgraph_ref.plan_ref)
    except (OSError, ValueError) as exc:
        raise PlanLiftError(
            f"plan {spec_id!r}: subgraph node {node_id!r} plan_ref "
            f"{subgraph_ref.plan_ref!r} failed to resolve: {exc}",
            plan_id=spec_id,
            node_id=node_id,
        ) from exc
    if not path.exists():
        raise PlanLiftError(
            f"plan {spec_id!r}: subgraph node {node_id!r} plan_ref "
            f"{subgraph_ref.plan_ref!r} does not exist (resolved path={path})",
            plan_id=spec_id,
            node_id=node_id,
        )


def _enforce_subgraph_port_contract(
    *,
    spec_id: str,
    node_id: str,
    outer_schema: NodeIOSchema,
    subgraph_ref: SubgraphReference,
    declared_inputs_present: bool,
    declared_outputs_present: bool,
) -> None:
    """Reject subgraph ``declared_inputs/outputs`` names the inner plan can't honor.

    The subgraph data contract (ADR-0217 §3.3.3) is **name-based**:
    :class:`SubgraphStrategy` reads ``outer_schema.outputs`` by name
    from the merged inner output dict, and the inner kernel reads
    ``inner_schema.inputs`` by name from the outer port registry.
    A name that exists on one side but not the other causes a
    silent drop at runtime (``merged_output[outer_name]`` is
    ``None`` / not-present, or the inner reads a name it never
    received).

    Lift-time rejection turns this into a boot-time failure with
    structured context so the operator fixes the bundle.

    Inputs contract: every name in ``outer_schema.inputs`` must
    exist in the union of inputs declared on any inner plan node
    reachable from the entry.

    Outputs contract: every name in ``outer_schema.outputs`` must
    exist in the union of outputs declared on any inner plan node
    reachable from the entry. The subgraph entry node itself may
    only declare a subset; downstream inner nodes produce the
    rest and merge into the outer output dict.

    Falls through silently when the inner plan cannot be loaded
    (``_require_subgraph_plan_exists`` already raised a structured
    error in that case; duplicating it here would just produce
    noise).
    """
    inner_plan = _load_subgraph_plan_for_contract(subgraph_ref)
    if inner_plan is None:
        return
    if declared_inputs_present:
        inner_in_names: set[str] = set()
        for n in inner_plan.nodes:
            inner_in_names |= {p.name for p in n.io_schema.inputs}
        unknown = [p.name for p in outer_schema.inputs if p.name not in inner_in_names]
        if unknown:
            raise PlanLiftError(
                f"plan {spec_id!r}: subgraph node {node_id!r} declared_inputs "
                f"{unknown!r} are not declared by any inner plan node; "
                f"the inner kernel cannot read them. inner_declared_inputs="
                f"{sorted(inner_in_names)}",
                plan_id=spec_id,
                node_id=node_id,
            )
    if declared_outputs_present:
        inner_out_names: set[str] = set()
        for n in inner_plan.nodes:
            inner_out_names |= n.io_schema.output_names()
        unknown = [p.name for p in outer_schema.outputs if p.name not in inner_out_names]
        if unknown:
            raise PlanLiftError(
                f"plan {spec_id!r}: subgraph node {node_id!r} declared_outputs "
                f"{unknown!r} are not produced by any inner plan node; "
                f"the subgraph will never emit them. inner_declared_outputs="
                f"{sorted(inner_out_names)}",
                plan_id=spec_id,
                node_id=node_id,
            )


def _load_subgraph_plan_for_contract(
    subgraph_ref: SubgraphReference,
) -> Plan | None:
    """Load the inner plan referenced by *subgraph_ref* for contract checks.

    Returns ``None`` when the plan cannot be loaded (missing file,
    malformed yaml, missing entry node). The contract check is
    best-effort; the inner-plan lift error gets surfaced
    separately by the boot-time ``plan_validation`` aggregator.
    """
    try:
        import yaml

        path = _bundle_yaml_path(subgraph_ref.plan_ref)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        spec = dict(raw)
        if "entry" not in spec and subgraph_ref.entry_node:
            spec["entry"] = subgraph_ref.entry_node
        return _lift_graph_spec_inner(spec)
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return None


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
            raise ValueError(f"binding must be a BindingKind or string, got {value!r}")
    raise ValueError(f"binding must be a BindingKind or string, got {type(value).__name__}")


def _binding_from_factory_or_binding(raw: Mapping[str, object]) -> BindingKind:
    """Pick the right binding for a BundleGraphSpec-style node.

    Three inputs in priority order:

    1. ``binding:`` — explicit :class:`BindingKind` (v2 schema).
    2. ``sub_spec_ref:`` — nested subgraph; the kernel recurses via
       :class:`SubgraphStrategy`. Legacy think/act yaml nests
       ``sub_spec_ref:`` under ``config:``, so check both surfaces.
       Wins over ``factory`` so a node like ``think.reason``
       (sub-spec only) recurses instead of dispatching a leaf
       executor that does not exist.
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
    """Build a :class:`NodeIOSchema` from yaml ``inputs``/``outputs`` declarations.

    Inputs and outputs are independent port namespaces. A name
    that appears on both sides is a **read+write alias** (e.g. an
    act subgraph reads ``decision`` from upstream and emits a
    stamped ``decision`` downstream) — :class:`NodeIOSchema`
    permits this within the schema-level uniqueness invariant
    (uniqueness is per-direction). Both sides are preserved so the
    lifter records the full emit/read contract, the kernel
    forwards a same-named upstream value into the subgraph via
    :class:`SubgraphStrategy`, and downstream wiring checks see
    the emitted port on the output side.
    """
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
        out.append(PortSpec(name=name))
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


_LEAF_PREDICATE_KINDS = frozenset({"eq", "ne", "in", "exists", "missing"})


def _coerce_when(raw: object) -> Predicate | None:
    """Coerce a YAML ``when`` value to :class:`Predicate` or ``None``.

    - ``None`` / ``True`` / ``"true"`` / ``""`` → ``None`` (unconditional)
    - :class:`Predicate` → pass-through
    - dict with ``kind`` → structured Predicate (D6 plan SDK path)
    - any other string → ``PlanLiftError``. The legacy string-DSL
      edge conditions silently evaluated to ``False`` and were the
      root cause of ``outcome=failure`` runs (see spec §0). The D4
      cutover rejects every string at lift time so a misroute never
      reaches runtime.
    """
    if raw is None:
        return None
    if isinstance(raw, Predicate):
        return raw
    if isinstance(raw, bool):
        return (
            None
            if raw
            else Predicate(
                kind="eq",
                port=PortRef(name="__never__"),
                value=True,
            )
        )
    if isinstance(raw, Mapping):
        return _parse_predicate_dict(raw)
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in ("true", "false", ""):
            return None
        raise PlanLiftError(
            f"string `when: {raw!r}` is no longer supported; "
            "use a typed Predicate dict (see ADR-0195 typed-port graph)",
        )
    return None


def _parse_predicate_dict(raw: Mapping[str, Any]) -> Predicate:
    """Parse a dict-shaped predicate into a :class:`Predicate`."""
    kind = str(raw.get("kind", ""))
    if not kind:
        raise PlanLiftError("predicate dict missing 'kind' field")
    bool_kinds = frozenset({"and", "or", "not"})
    if kind in bool_kinds:
        children_raw = raw.get("children", ())
        if not isinstance(children_raw, (list, tuple)):
            raise PlanLiftError(f"predicate kind={kind!r}: children must be a sequence")
        children = tuple(c for c in (_coerce_when(c) for c in children_raw) if c is not None)
        return Predicate(kind=kind, children=children)
    if kind in _LEAF_PREDICATE_KINDS:
        port_raw = raw.get("port")
        port = _parse_port_ref(port_raw) if port_raw is not None else None
        value = raw.get("value")
        return Predicate(kind=kind, port=port, value=value)
    raise PlanLiftError(f"unknown predicate kind: {kind!r}")


def _parse_port_ref(raw: object) -> PortRef:
    """Parse a ``port`` dict into a :class:`PortRef`."""
    if isinstance(raw, PortRef):
        return raw
    if isinstance(raw, Mapping):
        name = str(raw.get("name", ""))
        field = raw.get("field")
        return PortRef(name=name, field=str(field) if field is not None else None)
    raise PlanLiftError(f"port ref must be a dict or PortRef, got {type(raw).__name__}")


def validate_predicates(plan: Plan) -> None:
    """Validate all typed :class:`Predicate` edges against source-node schemas.

    Raises :class:`PlanLiftError` with structured context on first violation:

    - Leaf predicate references a port not in source node's ``io_schema.outputs``.
    - Leaf ``Predicate.field`` is not declared on the port's ``payload_type``.

    String ``when`` values (legacy DSL) are skipped — they have no typed
    structure to validate. Boolean combinators recurse on children.
    """
    for edge in plan.edges:
        if not isinstance(edge.when, Predicate):
            continue
        try:
            source_node = plan.node(edge.source)
        except KeyError:
            # Plan model_validator already rejects dangling edges;
            # guard here is defensive only.
            continue
        _validate_predicate_node(
            edge.when,
            source_node.io_schema,
            plan_id=plan.id,
            edge_id=f"{edge.source}->{edge.target}",
        )


def _validate_predicate_node(
    pred: Predicate,
    schema: NodeIOSchema,
    *,
    plan_id: str,
    edge_id: str,
) -> None:
    """Recursively validate one predicate tree against *schema*."""
    if pred.kind in _LEAF_PREDICATE_KINDS:
        if pred.port is None:
            raise PlanLiftError(
                f"leaf predicate kind={pred.kind!r} requires port",
                plan_id=plan_id,
                edge_id=edge_id,
            )
        port_name = pred.port.name
        if port_name not in schema.output_names():
            raise PlanLiftError(
                f"edge {edge_id!r}: predicate port {port_name!r} not in "
                f"source node outputs {sorted(schema.output_names())}",
                plan_id=plan_id,
                edge_id=edge_id,
                port_name=port_name,
            )
        port_spec = _find_port_spec(schema, port_name)
        if pred.port.field is not None:
            # Typed-port field SSOT: when the bundle declares a
            # ``payload_type`` for the source port, the predicate's
            # named field must exist on that payload type — this is a
            # hard fail-loud because the kernel can statically prove
            # the field reference is bogus. When the bundle omits
            # ``payload_type``, the port is treated as dynamic and
            # the field check is skipped (kernel resolves the field
            # at runtime via :class:`PortReader`). The legacy-bundle
            # escape hatch is intentional: forcing every port to
            # declare a BaseModel payload_type would break the typed-
            # port D4 cutover's gradual rollout.
            if port_spec is not None and port_spec.payload_type is not None:
                if pred.port.field not in port_spec.payload_type.model_fields:
                    raise PlanLiftError(
                        f"edge {edge_id!r}: port {port_name!r} payload type "
                        f"{port_spec.payload_type.__name__!r} has no field "
                        f"{pred.port.field!r}",
                        plan_id=plan_id,
                        edge_id=edge_id,
                        port_name=port_name,
                    )
        return
    for child in pred.children:
        _validate_predicate_node(
            child,
            schema,
            plan_id=plan_id,
            edge_id=edge_id,
        )


def _find_port_spec(schema: NodeIOSchema, name: str) -> PortSpec | None:
    for spec in (*schema.inputs, *schema.outputs):
        if spec.name == name:
            return spec
    return None


def _validate_termination(plan: Plan) -> None:
    """Ensure the plan has at least one termination policy.

    A plan terminates when any node has ``terminal=True`` OR any node's
    ``io_schema.terminal_predicate`` is not ``None``. Without a
    termination policy the kernel would run indefinitely.
    """
    for node in plan.nodes:
        if node.terminal:
            return
        if node.io_schema.terminal_predicate is not None:
            return
    raise PlanLiftError(
        f"plan {plan.id!r}: no termination policy — "
        "at least one node must have terminal=True or a terminal_predicate",
        plan_id=plan.id,
    )


__all__ = [
    "_validate_termination",
    "lift_executable_plan",
    "lift_graph_spec",
    "validate_predicates",
]
