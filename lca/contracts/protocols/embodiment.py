"""L1 Body / 行动执行协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.state import TypedState


@runtime_checkable
class Body(Protocol):
    """行动执行体：将 StructuredDecision 转化为 Observation。"""

    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation: ...
    def bind_transport(self, transport: AgentTransport) -> None: ...


@runtime_checkable
class FallbackPolicy(Protocol):
    """未知 action_type 的降级策略接口。

    由 Body 装饰器在捕获到 ToolExecutionError("未注册的 action_type") 时调用。
    """

    async def handle(
        self,
        decision: StructuredDecision,
        state: TypedState,
        action_registry: ActionRegistryProtocol | None = None,
    ) -> Observation: ...


# 过渡期 alias
FallbackHandler = FallbackPolicy
