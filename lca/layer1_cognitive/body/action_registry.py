"""ActionRegistry —— ActionOperation 的默认注册表实现（ADR-0015/0016）。

从 contracts 迁出：contracts 只保留 Protocol，具体路由表属于 L1 embodiment。
"""

from __future__ import annotations

from lca.contracts.action import ActionOperation, ActionRegistryProtocol


class ActionRegistry(ActionRegistryProtocol):
    """Action 能力注册表 —— 开闭原则的标准落地。

    无状态纯路由，不承载业务逻辑、不承载降级逻辑。
    降级属于韧性层职责，由 FallbackActionPolicy 独立处理。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ActionOperation] = {}

    def register(self, action_type: str, handler: ActionOperation) -> None:
        """注册一个 ActionOperation 到指定 action_type。"""
        self._handlers[action_type] = handler

    def resolve(self, action_type: str) -> ActionOperation | None:
        """解析 action_type 对应的 Operation；未注册时返回 None。"""
        return self._handlers.get(action_type)

    def allowed_action_types(self) -> list[str]:
        """返回所有已注册的 action_type 集合 —— Prompt / Schema / 测试的唯一事实来源。"""
        return sorted(self._handlers.keys())

    def is_registered(self, action_type: str) -> bool:
        """判断 action_type 是否已注册。"""
        return action_type in self._handlers
