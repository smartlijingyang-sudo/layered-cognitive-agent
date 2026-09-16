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
