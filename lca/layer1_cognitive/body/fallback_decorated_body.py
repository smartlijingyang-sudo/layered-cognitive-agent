"""FallbackDecoratedBody."""

from __future__ import annotations

from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols import AgentTransport, Body, FallbackPolicy
from lca.contracts.result import UnregisteredActionError
from lca.contracts.state import TypedState


class FallbackDecoratedBody(Body):
    def __init__(self, inner: Body, fallback_handler: FallbackPolicy) -> None:
        self._inner = inner
        self._fallback_handler = fallback_handler

    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation:
        try:
            return await self._inner.act(decision, state)
        except UnregisteredActionError:
            registry = getattr(self._inner, "action_registry", None)
            return await self._fallback_handler.handle(decision, state, registry)

    def bind_transport(self, transport: AgentTransport) -> None:
        self._inner.bind_transport(transport)
