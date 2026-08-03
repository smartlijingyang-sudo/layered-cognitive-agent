"""Hierarchical team process: supervisor owns consultation control plane."""

from __future__ import annotations

from lca.contracts.consultation import ConsultationState
from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.contracts.run_context import RunContext

_DEFAULT_DELEGATE_MAX_ATTEMPTS = 3


class HierarchicalStrategy(TeamProcessStrategy):
    """Supervisor-only path; consultation board carried via RunContext."""

    async def run(self, context: TeamContext, objective: str) -> Result:
        if context.supervisor is None:
            raise ValueError("Hierarchical 模式需要 Supervisor")
        if context.member_status is None:
            raise ValueError("Hierarchical 模式需要 MemberStatus board")
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
