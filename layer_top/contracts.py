统一认知执行体契约 — Worker 协议、Task 入参、Result 出参。

三者构成 Worker 协议的完整 I/O：
Task 是委托方传给 Worker 的认知意图载体，
Result 是 Worker 返回给委托方的认知产出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


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


@dataclass
class Result:
    """认知产出 — Worker.execute 的返回。

    output 与 error 互斥：有 error 表示失败（output 为 None），
    无 error 表示完成（output 可能为 None，无产出的完成也合法）。
    不混合基础设施关注点（追踪、步数、预算由运行时管）。
    """

    output: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """任务是否成功完成。"""
        return self.error is None

    @classmethod
    def completed(cls, output: str) -> Result:
        """构造成功 Result。"""
        return cls(output=output)

    @classmethod
    def failed(cls, error: str) -> Result:
        """构造失败 Result。"""
        return cls(error=error)


@runtime_checkable
class Worker(Protocol):
    """统一认知执行体 — Agent 与 MultiAgent 共同满足。

    一个方法，一个参数类型。resume / cancel 是具体类的可选能力，
    不强制到协议上。嵌套由类型系统自然实现：
    MultiAgent 实现此协议，members: list[Worker]，
    故 Team 可作为上层 Team 的成员。
    """

    async def execute(self, task: Task) -> Result: ...
