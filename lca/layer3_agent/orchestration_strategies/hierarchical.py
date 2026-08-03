"""Hierarchical team process: SUPERVISOR family entry (ADR-0027 / ADR-0029).

Strategy only creates a fresh ControlSession and runs the closed supervisor.
"""

from __future__ import annotations

from lca.contracts.consultation import ConsultationState
from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.protocols.orchestration import team_supervisor_mode
from lca.contracts.result import Result
from lca.contracts.routing import RoutingState
from lca.contracts.run_context import RunContext
from lca.contracts.supervisor_mode import mode_uses_consultation_session

_DEFAULT_DELEGATE_MAX_ATTEMPTS = 3


class HierarchicalStrategy(TeamProcessStrategy):
    """SUPERVISOR-family path: inject session, run supervisor agent."""

    async def run(self, context: TeamContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")

        mode = team_supervisor_mode(context)
        if mode is None:
            raise ValueError("Hierarchical 模式需要 TeamConfig.supervisor_mode")

        max_attempts = (
            context.config.delegate_max_attempts
            if context.config is not None
            else _DEFAULT_DELEGATE_MAX_ATTEMPTS
        )

        if mode_uses_consultation_session(mode):
            if context.member_status is None:
                raise ValueError("Consultation/Board mode 需要 MemberStatus board template")
            # Fresh board each team.run — clone via factory role_order if available.
            board = context.member_status
            session: ConsultationState | RoutingState = ConsultationState(
                member_status=board,
                teammates=list(context.teammates),
                delegate_max_attempts=max_attempts,
            )
        else:
            session = RoutingState(teammates=list(context.teammates))

        return await context.supervisor.run(objective, RunContext(session=session))
