"""Action 能力契约 —— Action Protocol + ActionRegistry Protocol。

L1 契约层：定义"什么是一个合法的 Agent 行动"以及"如何路由到对应处理器"。
全系统的唯一事实来源：Prompt 枚举、Schema 校验、执行分发均从此处派生。

具体注册表实现见 ``lca.layer1_cognitive.body.action_registry.ActionRegistry``（ADR-0015）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.decision import Decision, Observation
from lca.contracts.models.core.state import AgentState


@runtime_checkable
class Action(Protocol):
    """单一行动能力的操作接口（Strategy Pattern）。

    每种 action_type 对应一个独立实现，彼此零依赖、零共享可变状态。
    新增行动能力 = 新增一个 Operation + 一条注册，不修改任何既有代码路径。
    """

    async def execute(self, decision: Decision, state: AgentState) -> Observation: ...


@runtime_checkable
class ActionRegistryProtocol(Protocol):
    """Action 能力注册表接口。

    无状态纯路由，不承载业务逻辑、不承载降级逻辑。
    """

    def register(self, action_type: str, handler: Action) -> None: ...

    def get(self, action_type: str) -> Action | None: ...

    def resolve(self, action_type: str) -> Action: ...

    def allowed_action_types(self) -> list[str]: ...

    def is_registered(self, action_type: str) -> bool: ...

    def normalize_alias(self, name: str) -> str:
        """将 LLM 输出的别名归一化为规范 action_type。

        未识别的名称原样返回，交由 FallbackActionPolicy 降级。
        """
        ...
