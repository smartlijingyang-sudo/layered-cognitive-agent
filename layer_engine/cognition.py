"""认知协作者协议与交换数据对象。

Brain / Body / Memory 是 CognitiveEngine 的三个可插拔协作者：
- Brain：推理（看历史，出决策）
- Body：行动（执行决策，回观察）
- Memory：状态（跟踪历史，供 Brain 读取）

Decision / Observation / Turn / ToolCall 是三者之间的交换数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from layer_top.contracts import Task
from lca.contracts.role_team import RoleProfile


@dataclass
class ToolCall:
    """工具调用请求 — LLM 决定调用的工具名和参数。"""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    """认知决策 — Brain 的产出，告诉引擎下一步做什么。

    tool_calls 和 final_answer 互斥：
    有 final_answer → 循环结束；有 tool_calls → Body 执行。
    """

    tool_calls: list[ToolCall] = field(default_factory=list)
    final_answer: str | None = None


@dataclass
class Observation:
    """执行观察 — Body 的产出，工具调用的结果。"""

    output: str
    success: bool = True
    error: str | None = None


@dataclass
class Turn:
    """一轮认知循环 — 决策 + 观察。"""

    decision: Decision
    observation: Observation | None = None


@runtime_checkable
class Brain(Protocol):
    """推理引擎 — 看任务 + 身份 + 历史，出决策。

    reflect 是具体 Brain 的可选能力，不上协议
    （和 resume/cancel 同理：角色是组合时绑定的，不是协议强制的）。
    """

    async def think(
        self, task: Task, identity: RoleProfile, turns: list[Turn]
    ) -> Decision: ...


@runtime_checkable
class Body(Protocol):
    """行动执行器 — 执行决策中的工具调用，返回观察。"""

    async def act(self, decision: Decision) -> Observation: ...


@runtime_checkable
class Memory(Protocol):
    """对话状态 — 跟踪认知循环历史，供 Brain 读取。

    RAG / 长期检索是 Tool（Brain 决定何时检索），不是 Memory 的职责。
    Memory 只管对话循环内的短期记忆。
    """

    def turns(self) -> list[Turn]: ...

    def record(self, turn: Turn) -> None: ...
