"""lca 运行时控制工具（ADR-0268 §4）。

``lca.nothing_to_do`` 是 handoff 轮的静默结束信号。用户轮 wire 不暴露
它；模型在用户轮发出该调用时，由 ``unexposed_tool_block_observation``
回注错误（ADR-0268 §14.1、§14.2）。handoff 轮机制（调度器 +
developer 消息注入）由 ADR-0268 §6 定义，本模块只提供工具对象与
轮次过滤。
"""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool

IDENTIFIER = "lca.nothing_to_do"


class NothingToDoTool:
    """``lca.nothing_to_do``：结束 handoff 轮，不写 assistant 可见气泡。"""

    name: ClassVar[str] = IDENTIFIER
    namespace: ClassVar[str] = "lca"
    description: ClassVar[str] = (
        "结束当前 handoff 轮，不写 assistant 可见气泡。只在定时任务 handoff 轮可用。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    async def execute(self, args: dict[str, Any]) -> Observation:
        # ADR-0268 §4：runtime 结束本轮，不写可见气泡。handoff 注入机制
        # 尚未接线；任何到达这里的调用都会被轮次过滤挡住，真正的静默
        # 消费逻辑随 handoff 轮机制（§6）落地。
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=None,
            extra={"silent_handoff": True},
        )

    def validate(self, args: dict[str, Any]) -> str | None:
        return None


def build_tools() -> list[Tool]:
    """返回 ``lca`` 命名空间的工具集。"""
    return [NothingToDoTool()]


def filter_handoff_only_tools(items: tuple[Tool, ...], origin: str) -> tuple[Tool, ...]:
    """ADR-0268 §4：``lca.nothing_to_do`` 只在 handoff 轮可用。

    用户轮（``origin != "handoff"``）从 wire 上移除；模型仍发出该调用
    时，``unexposed_tool_block_observation`` 回注错误。
    """
    if origin == "handoff":
        return items
    return tuple(t for t in items if getattr(t, "name", "") != IDENTIFIER)
