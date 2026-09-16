"""Lift-time validators for predicates and termination policy.

Deep module behind :mod:`lca.framework.graph.lift.interface`.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.plan import Plan
from lca.contracts.protocols.graph.predicate import Predicate
from lca.framework.graph.lift.parsers import _LEAF_PREDICATE_KINDS


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
        if (
            pred.port.field is not None
            and port_spec is not None
            and port_spec.payload_type is not None
            and pred.port.field not in port_spec.payload_type.model_fields
        ):
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


def validate_termination(plan: Plan) -> None:
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


# Backward-compatible private alias for existing tests.
_validate_termination = validate_termination

__all__ = [
    "_validate_termination",
    "validate_predicates",
    "validate_termination",
]


def _validate_approval_resume_node(plan: Plan) -> None:
    """Fail-loud when HITL resume path is missing — outer + per-plan.

    PR-1 (closes 评审 §6.1 + G-1 hot path): HITL without a resume edge
    is unsafe — an interrupt can pause a run but never recover, so the
    next user command is dropped on the floor. This check fires at every
    ``lift_graph_spec`` call (including the boot-time ``validate_profile_plans``
    walk) so the operator sees the failure before the first run.

    PR-1b (ADR-0237) refines the check into two pieces because the
    gate moved into act_subgraph (spec §3.2 原位):

    (a) **Per-plan rule** — any plan that declares ``act.approve.gate``
        as one of its nodes must also declare
        ``intervene.resume → act.approve.gate`` in the same plan.
        The inner subgraph's gate has its own resume edge in
        :file:`bundles/act/act_subgraph.yaml`.

    (b) **Outer-level rule** — once the outer ``act.approve.gate``
        delegate is gone (PR-1b), the typed ``approval_routing`` port
        (bubbled out of act_subgraph via :class:`PortRegistry.exit_subgraph`,
        ADR-0217 §3.3.3) must be consumed by the outer plan. Otherwise
        an approve-rejected outcome has nowhere to land.
    """
    node_ids = {n.id for n in plan.nodes}
    if "act.approve.gate" in node_ids:
        resume_edge_present = any(
            e.source == "intervene.resume" and e.target == "act.approve.gate"
            for e in plan.edges
        )
        if not resume_edge_present:
            raise PlanLiftError(
                "act.approve.gate is declared but the cross-subgraph resume "
                "edge intervene.resume -> act.approve.gate is missing. "
                "Without it the HITL interrupt can pause a run but never recover.",
                plan_id=plan.id,
            )

    # Outer-level check (PR-1b): the outer plan (the one whose node set
    # does NOT contain act.approve.gate — only act.main does) must consume
    # approval_routing via at least one edge predicate. Detect by walking
    # every edge's predicate.
    if _outer_consumes_hitl_routing(plan):
        return
    # If the plan has no act.main node either, this is the inner subgraph
    # and there's no outer routing obligation.
    if "act.main" not in node_ids and "act.approve.gate" not in node_ids:
        return
    raise PlanLiftError(
        "outer plan must consume approval_routing.next_hint via at least "
        "one edge predicate. Without it the approve-rejected/approve-interrupt "
        "outcomes have nowhere to land once the gate is inside act_subgraph.",
        plan_id=plan.id,
    )


def _predicate_reads_routing_next_hint(pred: Predicate) -> bool:
    """Walk a predicate tree and report whether any leaf reads the routing
    port's ``next_hint`` field.

    The port name is ``approval_routing`` (renamed from ``routing`` per
    ADR-0237 / PR-1b to avoid the ``PortRegistry.last-write-wins``
    collision with the inner ``act.fanout``'s ``routing``). The check
    accepts either name so a future rename can swap back without
    rewriting the validator.
    """
    if pred is None:
        return False
    if pred.kind in ("and", "or"):
        return any(_predicate_reads_routing_next_hint(c) for c in pred.children)
    if pred.kind == "not":
        return bool(pred.children) and _predicate_reads_routing_next_hint(pred.children[0])
    if pred.port is None:
        return False
    return (
        pred.port.name in ("routing", "approval_routing")
        and pred.port.field == "next_hint"
    )


def _outer_consumes_hitl_routing(plan: Plan) -> bool:
    """True iff at least one edge predicate reads ``approval_routing.next_hint``."""
    return any(_predicate_reads_routing_next_hint(e.when) for e in plan.edges)


__all__ = [
    "_outer_consumes_hitl_routing",
    "_predicate_reads_routing_next_hint",
    "_validate_approval_resume_node",
    "_validate_termination",
    "validate_predicates",
    "validate_termination",
]
