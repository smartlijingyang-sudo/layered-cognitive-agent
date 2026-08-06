"""LeadStrategy — 有主导者团队路径（ADR-0030 / ADR-0034 / ADR-0035）。

构造期闭合：持有封闭 lead agent + 名册 + 可选咨询义务模板（board 为 None 即
自由 routing）。策略每次 run 新建 TeamAwareness——单一类型，无会话分裂，
不从任何运行期上下文解包——lead 与 coordination 同为 Governance。
"""

from __future__ import annotations

from lca.contracts.models.core.result import Result
from lca.contracts.models.team.member_status import MemberStatus
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness
from lca.contracts.protocols import AgentUnit, TeamStrategy


class LeadStrategy(TeamStrategy):
    """Lead path: fresh awareness per run, then execute the closed lead agent."""

    def __init__(
        self,
        lead: AgentUnit,
        roster: tuple[RoleProfile, ...],
        board: MemberStatus | None,
        delegate_max_attempts: int,
    ) -> None:
        self._lead = lead
        self._roster = roster
        self._board = board
        self._delegate_max_attempts = delegate_max_attempts

    async def run(self, objective: str) -> Result:
        duty = (
            ConsultDuty(member_status=self._board, max_attempts=self._delegate_max_attempts)
            if self._board is not None
            else None
        )
        awareness = TeamAwareness(teammates=list(self._roster), consult_duty=duty)
        return await self._lead.run(objective, RunContext(team_awareness=awareness))
