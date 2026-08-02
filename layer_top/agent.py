"""Agent — Worker 的单认知体实现。

Agent 直接持有 Brain/Body/Memory 三个协作者，自己编排认知循环：
perceive → think → act → update → 循环。

借鉴现有五层架构的 perceive→think→act→update 认知循环，
简化接口但不丢架构。不需要 CognitiveEngine 包装层。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from layer_top.contracts import Result, Task, Worker
from lca.contracts.role_team import RoleProfile


@dataclass
class Decision:
    """认知决策 — Brain 的产出。

    answer 非空表示认知完成，as_result 返回 Result。
    action 非空表示继续行动，Body 解释执行。
    二者互斥。
    """

    action: str = ""
    answer: str | None = None

    def as_result(self) -> Result | None:
        """若为结论，返回 Result；否则 None 表示继续行动。"""
        if self.answer is not None:
            return Result.completed(self.answer)
        return None


@dataclass
class Observation:
    """执行观察 — Body 的产出，工具调用的结果。"""

    output: str
    success: bool = True
    error: str | None = None


@dataclass
class CognitiveState:
    """认知上下文 — Agent 维护，传给 Brain.think。

    task 是当前任务，identity 是角色身份，
    history 是积累的观察记录。AgentState 的轻量替代。
    """

    task: Task
    identity: RoleProfile
    history: list[str] = field(default_factory=list)


@runtime_checkable
class Brain(Protocol):
    """推理引擎 — 看认知上下文，出决策。

    reflect 是具体 Brain 的可选能力，不上协议
    （和 resume/cancel 同理：角色是组合时绑定的，不是协议强制的）。
    """

    async def think(self, state: CognitiveState) -> Decision: ...


@runtime_checkable
class Body(Protocol):
    """行动执行器 — 执行决策，返回观察。

    工具调用的细节（哪个工具、什么参数）是 Body 内部的事。
    """

    async def act(self, decision: Decision) -> Observation: ...


@runtime_checkable
class Memory(Protocol):
    """对话状态 — 感知与记忆更新。

    perceive：从记忆中提取相关上下文，丰富 state。
    update：将决策和观察存入记忆，同时更新 state。
    RAG / 长期检索是 Tool（Brain 决定何时检索），不是 Memory 的职责。
    """

    async def perceive(self, state: CognitiveState) -> CognitiveState: ...

    async def update(
        self, state: CognitiveState, decision: Decision, observation: Observation
    ) -> None: ...


class Agent(Worker):
    """单认知体 — 直接编排 perceive→think→act→update 循环。

    Agent 自己就是引擎，不需要 CognitiveEngine 包装层。
    三协作者可独立替换，不影响循环逻辑。
    """

    def __init__(
        self,
        identity: RoleProfile,
        brain: Brain,
        body: Body,
        memory: Memory,
    ) -> None:
        self._identity = identity
        self._brain = brain
        self._body = body
        self._memory = memory

    async def execute(self, task: Task) -> Result:
        state = CognitiveState(task=task, identity=self._identity)
        state = await self._memory.perceive(state)

        while True:
            decision = await self._brain.think(state)
            if (result := decision.as_result()) is not None:
                return result
            observation = await self._body.act(decision)
            await self._memory.update(state, decision, observation)
