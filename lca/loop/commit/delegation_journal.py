"""Delegation journal commit seam (ADR-0194 P1-16).

Cognition prepares delegation cache-hit facts; loop layer commits via the bound
Session publish path. Unbound session → no-op (tests / offline).
"""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState
from lca.plugins.events.publishers._session_publish import (
    current_publish_session,
    publish_via_session,
)
from lca.plugins.events.publishers.delegation_cache.plugin import DelegationCachePlugin
from lca_kernel.events import TeamDelegationCacheHit


def commit_delegation_cache_hit(
    *,
    callee_role: str,
    subtask: str,
    step: int,
    state: AgentState | None = None,
) -> None:
    """Commit one ``team.delegation.cache_hit`` v2 fact; no-op when unbound."""
    del state
    if current_publish_session() is None:
        return
    publish_via_session(
        TeamDelegationCacheHit(
            callee_role=callee_role,
            subtask=subtask,
            step=step,
        ),
        producer=DelegationCachePlugin,
    )


__all__ = ["commit_delegation_cache_hit"]
