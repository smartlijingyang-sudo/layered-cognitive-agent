"""Action 能力契约 —— ActionOperation Protocol + ActionRegistry Protocol。

L1 契约层：定义"什么是一个合法的 Agent 行动"以及"如何路由到对应处理器"。
全系统的唯一事实来源：Prompt 枚举、Schema 校验、执行分发均从此处派生。

具体注册表实现见 ``lca.layer1_cognitive.body.action_registry.ActionRegistry``（ADR-0015）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.state import TypedState


@runtime_checkable
class ActionOperation(Protocol):
    """单一行动能力的操作接口（Strategy Pattern）。

    每种 action_type 对应一个独立实现，彼此零依赖、零共享可变状态。
    新增行动能力 = 新增一个 Operation + 一条注册，不修改任何既有代码路径。
    """

    async def execute(self, decision: StructuredDecision, state: TypedState) -> Observation: ...


# 过渡期 alias —— 下一主版本删除
ActionHandler = ActionOperation


@runtime_checkable
class ActionRegistryProtocol(Protocol):
    """Action 能力注册表接口。

    无状态纯路由，不承载业务逻辑、不承载降级逻辑。
    """

    def register(self, action_type: str, handler: ActionOperation) -> None: ...

    def resolve(self, action_type: str) -> ActionOperation | None: ...

    def allowed_action_types(self) -> list[str]: ...

    def is_registered(self, action_type: str) -> bool: ...
