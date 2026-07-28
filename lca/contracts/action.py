"""Action 能力契约 —— ActionHandler Protocol + ActionRegistry。

L1 契约层：定义"什么是一个合法的 Agent 行动"以及"如何路由到对应处理器"。
全系统的唯一事实来源：Prompt 枚举、Schema 校验、执行分发均从此处派生。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.state import TypedState


@runtime_checkable
class ActionHandler(Protocol):
    """单一行动能力的处理器接口（Strategy Pattern）。

    每种 action_type 对应一个独立实现，彼此零依赖、零共享可变状态。
    新增行动能力 = 新增一个 Handler + 一条注册，不修改任何既有代码路径。
    """

    async def execute(self, decision: StructuredDecision, state: TypedState) -> Observation: ...


class ActionRegistry:
    """Action 能力注册表 —— 开闭原则的标准落地。

    无状态纯路由，不承载业务逻辑、不承载降级逻辑。
    降级属于韧性层（L4）职责，由 FallbackActionHandler 独立处理。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, action_type: str, handler: ActionHandler) -> None:
        """注册一个 ActionHandler 到指定 action_type。"""
        self._handlers[action_type] = handler

    def resolve(self, action_type: str) -> ActionHandler | None:
        """解析 action_type 对应的 Handler；未注册时返回 None（交由韧性层降级）。"""
        return self._handlers.get(action_type)

    def allowed_action_types(self) -> list[str]:
        """返回所有已注册的 action_type 集合 —— Prompt / Schema / 测试的唯一事实来源。"""
        return sorted(self._handlers.keys())

    def is_registered(self, action_type: str) -> bool:
        """判断 action_type 是否已注册。"""
        return action_type in self._handlers
