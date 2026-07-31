"""L1 Body / 行动执行协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Decision, Observation
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.state import AgentState


@runtime_checkable
class Body(Protocol):
    """行动执行体：将 Decision 转化为 Observation。"""

    async def act(self, decision: Decision, state: AgentState) -> Observation: ...
    def bind_channel(self, transport: AgentTransport) -> None: ...


@runtime_checkable
class FallbackPolicy(Protocol):
    """未知 action_type 的降级策略接口。

    由 Body 装饰器在捕获到 ToolExecutionError("未注册的 action_type") 时调用。
    """

    async def handle(
        self,
        decision: Decision,
        state: AgentState,
        action_registry: ActionRegistryProtocol | None = None,
    ) -> Observation: ...
