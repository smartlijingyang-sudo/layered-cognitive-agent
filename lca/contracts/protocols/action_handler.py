"""ActionHandler Protocol（ADR-0074：插件化行动处理器）。

提取 `action_catalog.py` 中的硬编码 `_operation_for` 函数为可插拔的 ActionHandler。
每个 handler 知道如何为一个 ActionType（如 "respond"、"use_tool"）创建 Action 实现。
新增 action type = 注册新 handler，无需修改核心代码。

具体注册表实现见 `lca.cognition.body.action_registry.ActionRegistry`。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.protocols.action import Action
from lca.contracts.protocols.infra import (
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)


@runtime_checkable
class ActionHandler(Protocol):
    """Action 实现的工厂。

    ADR-0074：将硬编码的 `_operation_for` 提取为可插拔的 handler。
    每个 handler 知道如何为一个 ActionType 创建 Action（如 "respond"、"use_tool"）。
    新增 action type = 注册新 handler，无需修改核心代码路径。

    插件只替换实现，不在循环上开洞（宪法 C6）。
    """

    def create(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistryProtocol,
    ) -> Action | None:
        """创建给定依赖的 Action 实现。

        Args:
            tool_registry: 工具注册表，提供 tool 访问能力。
            safe_executor: 安全执行器，提供受控的工具执行环境。
            transport_registry: 传输注册表，提供通信通道访问。

        Returns:
            对应 ActionType 的 Action 实现，或 None 表示无法创建。
        """
        ...


@runtime_checkable
class ActionHandlerRegistry(Protocol):
    """ActionHandler 实现注册表。

    管理 ActionType 到 ActionHandler 的映射，支持动态注册和解析。
    替代硬编码的 dispatch 逻辑（ADR-0074）。
    """

    def register(self, action_type: str, handler: ActionHandler) -> None:
        """注册给定 action type 的 handler，并保留其唯一所有权。

        Args:
            action_type: ActionType 字符串标识（如 "respond"、"use_tool"）。
            handler: 对应 action type 的 ActionHandler 实现。

        Raises:
            KeyError: 当同一 action type 已有 handler 所有者时。
            ValueError: 当 action type 为空或不是字符串时。
        """
        ...

    def resolve(self, action_type: str) -> ActionHandler | None:
        """解析给定 action type 的 handler。

        Args:
            action_type: ActionType 字符串标识。

        Returns:
            对应的 ActionHandler，或 None 表示未注册。
        """
        ...

    def registered(self) -> tuple[str, ...]:
        """返回稳定的已注册 ActionType 快照（ADR-0076 §五）。

        BodyComposer uses this snapshot to iterate over the available
        ActionTypes and filter them through the plan-derived
        :class:`ActionAuthorityPlan`; the registry itself does not own
        the allow-list.
        """
        ...


__all__ = ["ActionHandler", "ActionHandlerRegistry"]
