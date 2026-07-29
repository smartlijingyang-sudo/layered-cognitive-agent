"""SimpleBody —— 通过 ActionRegistry 分发行动。"""

from __future__ import annotations

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols import (
    AgentTransport,
    Body,
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.result import UnregisteredActionError
from lca.contracts.state import TypedState
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.action_registry import ActionRegistry


class SimpleBody(Body):
    """Default ``Body`` implementation — dispatches actions via ``ActionRegistry``.

    Resolves the ``action_type`` from a ``StructuredDecision`` through the
    action registry and delegates execution to the registered
    ``ActionOperation``.  Supports flexible construction: callers may inject
    a pre-built ``ActionRegistry``, or provide ``ToolRegistry`` +
    ``SafeExecutor`` and let the body build the registry automatically.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        safe_executor: SafeExecutor | None = None,
        transport_registry: TransportRegistryProtocol | None = None,
        transport: AgentTransport | None = None,
        action_registry: ActionRegistryProtocol | None = None,
    ) -> None:
        if transport_registry is not None:
            self.transport_registry = transport_registry
        elif transport is not None:
            registry = TransportRegistry()
            registry.register(transport)
            self.transport_registry = registry
        else:
            self.transport_registry = TransportRegistry()

        if action_registry is not None:
            self.action_registry = action_registry
        elif tool_registry is not None and safe_executor is not None:
            self.action_registry = build_default_action_registry(
                tool_registry, safe_executor, self.transport_registry
            )
        else:
            self.action_registry = ActionRegistry()

        self.tool_registry = tool_registry
        self.safe_executor = safe_executor

    def bind_transport(self, transport: AgentTransport) -> None:
        self.transport_registry.register(transport)

    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation:
        handler = self.action_registry.resolve(decision.action_type)
        if handler is None:
            raise UnregisteredActionError(decision.action_type)
        result: Observation = await handler.execute(decision, state)
        return result
