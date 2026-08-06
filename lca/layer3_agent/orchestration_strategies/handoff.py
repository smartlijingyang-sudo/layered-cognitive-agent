"""RaceStrategy — PEER: sequential try, first COMPLETED wins (no output chaining).

命名说明：旧名 HandoffStrategy 与 ActionType.HANDOFF（非阻塞 body action）
概念冲突，重命名为 RaceStrategy 以准确表达"竞速"语义。
"""

from __future__ import annotations

from lca.contracts.models.core.result import Result
from lca.contracts.protocols import TeamStage, TeamStrategy
from lca.layer3_agent.member_invoke import invoke_members_sequential


class RaceStrategy(TeamStrategy):
    """PEER topology: stop at the first member that completes."""

    def __init__(self, stage: TeamStage) -> None:
        self._stage = stage

    async def run(self, objective: str) -> Result:
        return await invoke_members_sequential(
            self._stage,
            objective,
            pass_output_as_next_task=False,
            stop_on_first_completed=True,
        )


# 向后兼容别名（下一大版本移除）
HandoffStrategy = RaceStrategy
