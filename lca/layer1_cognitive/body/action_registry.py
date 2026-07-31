"""ActionRegistry —— Action 的默认注册表实现（ADR-0015/0016）。

从 contracts 迁出：contracts 只保留 Protocol，具体路由表属于 L1 embodiment。
"""

from __future__ import annotations

from lca.contracts.action import Action, ActionRegistryProtocol
from lca.layer0_infra.component_registry import NamedRegistry


class ActionRegistry(NamedRegistry[Action], ActionRegistryProtocol):
    """Action 能力注册表 —— 开闭原则的标准落地。

    无状态纯路由，不承载业务逻辑、不承载降级逻辑。
    降级属于韧性层职责，由 FallbackActionPolicy 独立处理。
    """

    _REGISTRY_KIND = "action_type"

    def __init__(self) -> None:
        NamedRegistry.__init__(self)
        self._aliases: dict[str, str] = {}

    def register(self, action_type: str, handler: Action) -> None:
        """注册一个 Action 到指定 action_type。"""
        self._entries[action_type] = handler
        self._aliases[action_type] = action_type

    def get(self, action_type: str) -> Action | None:
        return self._entries.get(action_type)

    def register_alias(self, alias: str, canonical: str) -> None:
        """注册别名映射：alias → canonical action_type。"""
        self._aliases[alias] = canonical

    def allowed_action_types(self) -> list[str]:
        """返回所有已注册的 action_type 集合 —— Prompt / Schema / 测试的唯一事实来源。"""
        return sorted(self._entries.keys())

    def is_registered(self, action_type: str) -> bool:
        """判断 action_type 是否已注册。"""
        return action_type in self._entries

    def normalize_alias(self, name: str) -> str:
        """将 LLM 输出的别名归一化为规范 action_type；未识别则原样返回。"""
        return self._aliases.get(name, name)
