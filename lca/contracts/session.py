"""ControlSession — single RunContext/AgentState slot for supervisor planes."""

from __future__ import annotations

from typing import TypeAlias

from lca.contracts.consultation import ConsultationState
from lca.contracts.routing import RoutingState

ControlSession: TypeAlias = ConsultationState | RoutingState


def as_consultation(session: ControlSession | None) -> ConsultationState | None:
    """Narrow session to ConsultationState; None if absent or wrong kind."""
    if session is None:
        return None
    if isinstance(session, ConsultationState):
        return session
    return None


def as_routing(session: ControlSession | None) -> RoutingState | None:
    """Narrow session to RoutingState; None if absent or wrong kind."""
    if session is None:
        return None
    if isinstance(session, RoutingState):
        return session
    return None


def require_consultation(session: ControlSession | None) -> ConsultationState:
    c = as_consultation(session)
    if c is None:
        raise ValueError("ConsultationState required on session")
    return c


def require_routing(session: ControlSession | None) -> RoutingState:
    r = as_routing(session)
    if r is None:
        raise ValueError("RoutingState required on session")
    return r
