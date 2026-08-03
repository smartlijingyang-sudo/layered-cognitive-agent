"""Hierarchical team process: SUPERVISOR family entry (ADR-0027).

Industry slot: Crew hierarchical / LangGraph supervisor node.
Planes:
- CONSULTATION → ``ConsultationState`` + optional settlement gate
- ROUTING → ``RoutingState`` free PM (no settlement board)
"""

from __future__ import annotations

from lca.contracts.consultation import ConsultationState
from lca.contracts.orchestration_taxonomy import SupervisorPlane
from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.contracts.routing import RoutingState
from lca.contracts.run_context import RunContext

_DEFAULT_DELEGATE_MAX_ATTEMPTS = 3


class HierarchicalStrategy(TeamProcessStrategy):
    """SUPERVISOR-family path: inject session, run supervisor agent."""

    async def run(self, context: TeamContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")

        plane = (
            context.config.supervisor_plane
            if context.config is not None
            else SupervisorPlane.CONSULTATION
        )
        if plane is SupervisorPlane.ROUTING:
            ctx = RunContext(
                routing=RoutingState(teammates=list(context.teammates)),
            )
            return await context.supervisor.run(objective, ctx)

        if context.member_status is None:
            raise ValueError("Consultation plane 需要 MemberStatus board")
        max_attempts = (
            context.config.delegate_max_attempts
            if context.config is not None
            else _DEFAULT_DELEGATE_MAX_ATTEMPTS
        )
        ctx = RunContext(
            consultation=ConsultationState(
                member_status=context.member_status,
                teammates=list(context.teammates),
                delegate_max_attempts=max_attempts,
            ),
        )
        return await context.supervisor.run(objective, ctx)
