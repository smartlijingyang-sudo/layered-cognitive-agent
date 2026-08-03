"""LeadStrategy — team path with TeamLead (ADR-0030).

Strategy only creates a fresh control session and runs the closed lead agent.
"""

from __future__ import annotations

from lca.contracts.consultation import ConsultationState
from lca.contracts.protocols import TeamContext, TeamStrategy
from lca.contracts.protocols.orchestration import team_lead_mandate
from lca.contracts.result import Result
from lca.contracts.routing import RoutingState
from lca.contracts.run_context import RunContext
from lca.contracts.team_coordination import mandate_uses_consultation_session

_DEFAULT_DELEGATE_MAX_ATTEMPTS = 3


class LeadStrategy(TeamStrategy):
    """Lead path: inject session, run lead agent."""

    async def run(self, context: TeamContext, objective: str) -> Result:
        if context.lead is None:
            raise ValueError("Lead 路径需要 TeamLead")

        mandate = team_lead_mandate(context)
        if mandate is None:
            raise ValueError("Lead 路径需要 TeamConfig.lead_mandate")

        max_attempts = (
            context.config.delegate_max_attempts
            if context.config is not None
            else _DEFAULT_DELEGATE_MAX_ATTEMPTS
        )

        if mandate_uses_consultation_session(mandate):
            if context.member_status is None:
                raise ValueError("Consult/Board mandate 需要 MemberStatus board template")
            board = context.member_status
            session: ConsultationState | RoutingState = ConsultationState(
                member_status=board,
                teammates=list(context.teammates),
                delegate_max_attempts=max_attempts,
            )
        else:
            session = RoutingState(teammates=list(context.teammates))

        return await context.lead.run(objective, RunContext(session=session))
