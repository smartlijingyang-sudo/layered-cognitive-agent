"""CognitiveEngine — 编排 Brain/Body/Memory 的认知循环。

Agent 将认知工作委派给 CognitiveEngine，
引擎内部用 Brain 推理、Body 行动、Memory 记忆，循环直到产出最终答案。

替代现有 CognitiveRuntime，但保留三协作者可插拔性。
引擎自身只管循环编排，不关心推理细节、执行细节、记忆策略。
"""

from __future__ import annotations

from layer_engine.cognition import Brain, Body, Memory, Turn
from layer_top.contracts import Task
from lca.contracts.role_team import RoleProfile

DEFAULT_MAX_STEPS = 20


class CognitiveEngine:
    """认知引擎 — 编排 Brain/Body/Memory 的 ReAct 循环。

    循环逻辑：brain.think → 若 final_answer 返回；否则 body.act → memory.record → 循环。
    三协作者可独立替换，不影响循环逻辑。
    """

    def __init__(
        self, brain: Brain, body: Body, memory: Memory
    ) -> None:
        self._brain = brain
        self._body = body
        self._memory = memory

    async def run(self, task: Task, identity: RoleProfile) -> str:
        while True:
            decision = await self._brain.think(
                task, identity, self._memory.turns()
            )
            if decision.final_answer is not None:
                return decision.final_answer
            observation = await self._body.act(decision)
            self._memory.record(
                Turn(decision=decision, observation=observation)
            )
