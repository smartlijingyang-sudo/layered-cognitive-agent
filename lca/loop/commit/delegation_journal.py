"""Delegation cache-hit commit seam (ADR-0194 P1-16).

Cognition prepares delegation cache-hit facts; loop layer commits via
:class:`FactGateway` (``publish_ep_bound``). Unbound session → no-op.
"""

from __future__ import annotations

from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.loop.fact_gateway import AppendReceipt
from lca.loop.fact_gateway import publish_ep_bound


def commit_delegation_cache_hit(
    *,
    callee_role: str,
    subtask: str,
    step: int,
    state: AgentState | None = None,
    session: object | None = None,
    actor: str = "delegation",
) -> AppendReceipt | None:
    """Commit one ``team.delegation.cache_hit`` spine fact; no-op when unbound."""
    return publish_ep_bound(
        "team.delegation.cache_hit",
        {
            "callee_role": callee_role,
            "subtask": subtask,
            "step": step,
        },
        state=state,
        session=session,
        actor=actor,
    )


__all__ = ["commit_delegation_cache_hit"]
