"""LeadStrategy — 有主导者团队路径（ADR-0030 / ADR-0034）。

构造期闭合：持有封闭 lead agent + mandate + 名册 + board 模板。
策略只在每次 run 时新建控制会话（ConsultationState / RoutingState），
不从任何运行期上下文解包——lead 与 coordination 同为 Governance。
"""

from __future__ import annotations

from lca.contracts.consultation import ConsultationState
from lca.contracts.member_status import MemberStatus
from lca.contracts.protocols import AgentUnit, TeamStrategy
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile
from lca.contracts.routing import RoutingState
from lca.contracts.run_context import RunContext
from lca.contracts.team_coordination import LeadMandate, mandate_uses_consultation_session


class LeadStrategy(TeamStrategy):
    """Lead path: fresh session per run, then execute the closed lead agent."""

    def __init__(
        self,
        lead: AgentUnit,
        mandate: LeadMandate,
        roster: tuple[RoleProfile, ...],
        board: MemberStatus | None,
        delegate_max_attempts: int,
    ) -> None:
        if mandate_uses_consultation_session(mandate) and board is None:
            raise ValueError("Consult/Board mandate 需要 MemberStatus board template")
        self._lead = lead
        self._mandate = mandate
        self._roster = roster
        self._board = board
        self._delegate_max_attempts = delegate_max_attempts

    async def run(self, objective: str) -> Result:
        session: ConsultationState | RoutingState
        if mandate_uses_consultation_session(self._mandate):
            board = self._board
            if board is None:  # 构造期不变量已保证；防御性守卫
                raise ValueError("Consult/Board mandate 需要 MemberStatus board template")
            session = ConsultationState(
                member_status=board,
                teammates=list(self._roster),
                delegate_max_attempts=self._delegate_max_attempts,
            )
        else:
            session = RoutingState(teammates=list(self._roster))
        return await self._lead.run(objective, RunContext(session=session))
