"""SimpleBody —— L1 Body 实现，通过 ActionRegistry 分发行动。"""

from __future__ import annotations

from lca.contracts.action import ActionRegistry
from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols import AgentTransport, Body, SafeExecutor, ToolRegistry
from lca.contracts.result import ToolExecutionError
from lca.contracts.state import TypedState
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.action_handlers import build_default_action_registry


class SimpleBody(Body):
    """通过 ActionRegistry 路由 action_type 到对应 Handler。

    新增行动能力只需注册新 Handler 到 ActionRegistry，
    SimpleBody 本身不感知具体 action_type 集合。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        safe_executor: SafeExecutor | None = None,
        transport_registry: TransportRegistry | None = None,
        transport: AgentTransport | None = None,
        action_registry: ActionRegistry | None = None,
    ):
        # 解析 transport_registry
        if transport_registry is not None:
            self.transport_registry = transport_registry
        elif transport is not None:
            registry = TransportRegistry()
            registry.register(transport)
            self.transport_registry = registry
        else:
            self.transport_registry = TransportRegistry()

        # 解析 action_registry：优先使用显式传入的；否则从依赖构建默认注册表
        if action_registry is not None:
            self.action_registry = action_registry
        elif tool_registry is not None and safe_executor is not None:
            self.action_registry = build_default_action_registry(
                tool_registry, safe_executor, self.transport_registry
            )
        else:
            self.action_registry = ActionRegistry()

        # 保留引用供外部访问（向后兼容）
        self.tool_registry = tool_registry
        self.safe_executor = safe_executor

    def bind_transport(self, transport: AgentTransport) -> None:
        self.transport_registry.register(transport)

    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation:
        handler = self.action_registry.resolve(decision.action_type)
        if handler is None:
            raise ToolExecutionError(f"未注册的 action_type: {decision.action_type}")
        result: Observation = await handler.execute(decision, state)
        return result
