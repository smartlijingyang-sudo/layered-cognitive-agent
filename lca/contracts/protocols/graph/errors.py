"""Typed plan-lift errors.

All errors raised during plan construction carry structured context
(plan_id, node_id, edge_id, port_name) so debug never relies on
log search. Runtime errors raise :class:`UnsetPortError` /
:class:`UnknownFieldError`, both subclasses of :class:`PlanLiftError`
(semantically: "the plan's static contract was violated at runtime").
"""

from __future__ import annotations


class PlanLiftError(ValueError):
    """Raised at plan construction when:

    - a Predicate references a port the source node doesn't declare
    - a Predicate.field doesn't exist on the port's payload_type
    - a node's required input port is never produced by any predecessor
    - an edge's ``from`` node isn't in the plan
    - the plan has no termination policy
    """

    def __init__(
        self,
        reason: str,
        *,
        plan_id: str | None = None,
        node_id: str | None = None,
        edge_id: str | None = None,
        port_name: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.plan_id = plan_id
        self.node_id = node_id
        self.edge_id = edge_id
        self.port_name = port_name


class UnsetPortError(PlanLiftError):
    """Runtime: a predicate read a port that no node so far has written."""


class UnknownFieldError(PlanLiftError):
    """Runtime: a port's payload_type does not declare the requested field.

    Should be impossible post-lift (lift validates this); defensive only.
    """


__all__ = ["PlanLiftError", "UnknownFieldError", "UnsetPortError"]
