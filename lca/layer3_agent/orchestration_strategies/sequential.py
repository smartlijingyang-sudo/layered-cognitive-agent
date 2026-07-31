"""SequentialStrategy —— 成员顺序执行，输出传递给下一个成员。

L3 层职责：
    最简单的链式编排：A → B → C，每个成员的输出
    作为下一个成员的输入任务。全部成员依次执行完毕后
    返回最后一个成员的结果。
"""

from __future__ import annotations

from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_members_sequential


class SequentialStrategy(TeamProcessStrategy):
    """顺序链式编排：成员依次执行，输出传递给下一个成员。"""

    async def run(self, context: TeamContext, objective: str) -> Result:
        return await invoke_members_sequential(
            context, objective, pass_output_as_next_task=True, stop_on_first_completed=False
        )
