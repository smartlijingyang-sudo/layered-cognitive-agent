"""HandoffStrategy —— 成员顺序传递，首个完成者胜出。

L3 层职责：
    类似 Sequential 但语义不同：成员依次尝试处理同一任务，
    第一个成功完成的成员即返回结果（不传递输出给下一个）。
    适用于"谁先做完算谁的"的竞争场景。
"""

from __future__ import annotations

from lca.contracts.protocols import TeamContext, TeamProcessStrategy
from lca.contracts.result import Result
from lca.layer3_agent.member_invoke import invoke_members_sequential


class HandoffStrategy(TeamProcessStrategy):
    """交接编排：成员依次尝试，首个完成者胜出（不传递输出）。"""

    async def run(self, context: TeamContext, objective: str) -> Result:
        return await invoke_members_sequential(
            context, objective, pass_output_as_next_task=False, stop_on_first_completed=True
        )
