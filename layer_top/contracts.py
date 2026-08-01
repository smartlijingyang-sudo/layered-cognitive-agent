"""统一认知执行体契约 — Worker 协议与 Task 参数对象。

重构 AgentUnit / TeamUnit 双协议为单一 Worker 协议，
Task 作为对象形式参数取代裸字符串，支持递归嵌套组合。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from lca.contracts.result import Result


@dataclass
class Task:
    """认知任务 — 委托意图与认知上下文的载体，Worker 的唯一入参。

    五个字段映射五种真实委托场景，不混合基础设施关注点
    （追踪、预算、状态由运行时管）：
    - instruction: 做什么
    - expected_output: 做成什么样
    - context: 基于什么（前置产出）
    - delegator: 谁派的
    - deadline: 何时要
    """

    instruction: str
    expected_output: str = ""
    context: list[str] = field(default_factory=list)
    delegator: str = ""
    deadline: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Worker(Protocol):
    """统一认知执行体 — Agent 与 MultiAgent 共同满足。

    一个方法，一个参数类型。resume / cancel 是具体类的可选能力，
    不强制到协议上。嵌套由类型系统自然实现：
    TeamWorker 实现此协议，members: list[Worker]，
    故 Team 可作为上层 Team 的成员。
    """

    async def execute(self, task: Task) -> Result: ...
