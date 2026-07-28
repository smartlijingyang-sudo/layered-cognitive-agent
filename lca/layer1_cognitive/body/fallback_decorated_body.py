"""FallbackDecoratedBody —— Body 的降级装饰器。

将"未知 action_type 时降级"从 Runtime Loop 下沉到 Body 层，
符合装饰器模式：Loop 只调用 body.act()，不感知降级逻辑。

降级发生与否通过 Observation.extra[FALLBACK_DEGRADATION_KEY] 传递，
由 StepOutcomePolicy 在 Loop 外层解读，Loop 本身不认识这个 key。
"""

from __future__ import annotations

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols import AgentTransport, Body, FallbackHandler
from lca.contracts.result import ToolExecutionError
from lca.contracts.state import TypedState


class FallbackDecoratedBody(Body):
    """Body 装饰器：捕获"未注册的 action_type"错误并委托给 FallbackHandler。

    Loop 里只剩 ``await self.body.act(decision, state)``，
    不再出现 _act_with_fallback、局部 import、字符串前缀判断。
    """

    def __init__(self, inner: Body, fallback_handler: FallbackHandler) -> None:
        self._inner = inner
        self._fallback_handler = fallback_handler

    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation:
        try:
            return await self._inner.act(decision, state)
        except ToolExecutionError as err:
            if not str(err).startswith("未注册的 action_type:"):
                raise
            registry: ActionRegistryProtocol | None = getattr(self._inner, "action_registry", None)
            return await self._fallback_handler.handle(decision, state, registry)

    def bind_transport(self, transport: AgentTransport) -> None:
        self._inner.bind_transport(transport)
