"""SimpleBody —— 通过 ActionRegistry 分发行动。"""

from __future__ import annotations

from lca.contracts.atoms.enums import ActionScope
from lca.contracts.atoms.semantic_keys import OBS_DEGRADED_FROM
from lca.contracts.models.core.decision import Decision, Observation
from lca.contracts.models.core.result import UnregisteredActionError
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import (
    AgentTransport,
    Body,
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.action import ActionRegistryProtocol
from lca.layer0_infra.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.action_registry import ActionRegistry


class SimpleBody(Body):
    """Default ``Body`` implementation — dispatches actions via ``ActionRegistry``.

    Resolves the ``action_type`` from a ``Decision`` through the
    action registry and delegates execution to the registered
    ``Action``.  Supports flexible construction: callers may inject
    a pre-built ``ActionRegistry``, or provide ``ToolRegistry`` +
    ``SafeExecutor`` and let the body build the registry automatically.

    契约不变量：只分发词表内的 ``action_type``——越界决策应已在防腐层
    （``DegradationPolicy``）完成改写；到达这里仍越界属于契约违例，
    以 ``UnregisteredActionError`` 明确拒绝。被降级改写的决策会将其
    ``degraded_from`` 溯源传播到产出的 ``Observation`` 上。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        safe_executor: SafeExecutor | None = None,
        transport_registry: TransportRegistryProtocol | None = None,
        transport: AgentTransport | None = None,
        action_registry: ActionRegistryProtocol | None = None,
        *,
        action_scope: ActionScope = ActionScope.SOLO,
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
                tool_registry,
                safe_executor,
                self.transport_registry,
                scope=action_scope,
            )
        else:
            self.action_registry = ActionRegistry()

        self.tool_registry = tool_registry
        self.safe_executor = safe_executor

    async def act(self, decision: Decision, state: AgentState) -> Observation:
        handler = self.action_registry.get(decision.action_type)
        if handler is None:
            raise UnregisteredActionError(decision.action_type)
        observation = await handler.execute(decision, state)
        return self._propagate_degradation(decision, observation)

    @staticmethod
    def _propagate_degradation(decision: Decision, observation: Observation) -> Observation:
        """把决策的降级溯源传播到 Observation，供 hook 与终止策略观测。"""
        if decision.degraded_from is None:
            return observation
        observation.degraded_from = decision.degraded_from
        observation.extra[OBS_DEGRADED_FROM] = decision.degraded_from
        return observation
