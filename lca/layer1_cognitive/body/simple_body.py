"""SimpleBody —— 通过 ActionRegistry 分发行动。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.atoms.enums import ActionScope, ActionType
from lca.contracts.atoms.semantic_keys import OBS_DEGRADED_FROM
from lca.contracts.models.core.decision import Decision, Observation
from lca.contracts.models.core.execution import ExecutionEnvelope
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
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.action_handlers import record_decision_made
from lca.layer1_cognitive.body.action_registry import ActionRegistry
from lca.layer1_cognitive.transport_registry_factory import build_transport_registry


class SimpleBody(Body):
    """Default ``Body`` implementation — dispatches actions via ``ActionRegistry``.

    Resolves the ``action_type`` from a ``Decision`` through the
    action registry and delegates execution to the registered
    ``Action``.  Supports flexible construction: callers may inject
    a pre-built ``ActionRegistry``, or provide ``ToolRegistry`` +
    ``SafeExecutor`` and let the body build the registry automatically.

    契约不变量（v3 §5.3 / §9.1 / PR6 / PR10）：
    - ``act`` 必须收到 envelope；envelope 缺失 → ``UnregisteredActionError``。
    - 协议边界派生事件：``ActionDegraded`` 在 ``act`` 末尾直接 ``record()``，
      不再走 hook 派生（v3 §4.4）。
    - ``finalize`` 是 Body finalize 钩子，OfficeWorksSealer 等手平面副作用
      从这里调用；不在 ``act`` 内部。
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
        seal_office_works_fn: Callable[..., Any] | None = None,
    ) -> None:
        if transport_registry is not None:
            self.transport_registry = transport_registry
        elif transport is not None:
            self.transport_registry = build_transport_registry(transport)
        else:
            self.transport_registry = build_transport_registry()

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
        # v3 §9.2: OfficeWorksSealer 副作用点迁到 Body.finalize；
        # 默认调用 layer0 的 seal_office_works，测试可注入替代。
        self._seal_office_works_fn = seal_office_works_fn

    async def act(
        self,
        decision: Decision,
        state: AgentState,
        envelope: ExecutionEnvelope | None = None,
    ) -> Observation:
        """执行决策：分发到对应 ActionRegistry handler（v3 §9.1 / PR6）。

        The protocol signature is ``(decision, state)``; the
        ``envelope`` kwarg is reserved for PR6 callers that mint an
        envelope upstream.  When omitted we mint a minimal envelope
        from the first tool call so the body-side contract stays
        closed.
        """
        from lca.contracts.models.core.execution import envelope_from_decision

        if envelope is None:
            tool_calls = list(getattr(decision, "tool_calls", []) or [])
            tool_name = tool_calls[0].tool_name if tool_calls else "unknown"
            arguments = tool_calls[0].arguments if tool_calls else {}
            envelope = envelope_from_decision(tool_name, arguments)
        handler = self.action_registry.get(decision.action_type)
        if handler is None:
            raise UnregisteredActionError(decision.action_type)
        record_decision_made(decision, state)
        observation = await handler.execute(decision, state)
        observation = self._propagate_degradation(decision, observation)
        self._maybe_record_action_degraded(decision, observation, state)
        return observation

    async def finalize(self, observation: Observation, state: AgentState) -> None:
        """手平面 finalize（v3 §9.2：OfficeWorksSealer 迁移点）。

        当前 turn 即将关闭（RESPOND / STOP / ASK_HUMAN）或到达预算上限时
        触发；调用方在 _loop 内调用。
        """
        from lca.contracts.models.core.budget import TERMINAL_RESERVE_STEPS

        last_decision = state.history[-1].decision if state.history else None
        should_seal = last_decision is not None and last_decision.action_type in {
            ActionType.RESPOND,
            ActionType.STOP,
            ActionType.ASK_HUMAN,
        }
        if not should_seal:
            max_steps = state.budget.max_steps or 0
            should_seal = state.step >= max(0, max_steps - TERMINAL_RESERVE_STEPS)
        if should_seal and self._seal_office_works_fn is not None:
            await self._seal_office_works_fn()

    def _maybe_record_action_degraded(
        self, decision: Decision, observation: Observation, state: AgentState
    ) -> None:
        """协议边界派生事件（v3 §4.4 + §10）。

        Decision.degraded_from 不为空 + Observation.success=True → 由
        ``lca.layer2_runtime.event_emission`` 派生 ``ActionDegraded``；
        我们只保留溯源传播（``_propagate_degradation``），不再在 body
        里直接 emit（边界守卫：单一发射点是 event_emission）。
        """
        # Emit path lives in event_emission; body is responsible for
        # surfacing the degradation marker on Observation only.
        return

    @staticmethod
    def _propagate_degradation(decision: Decision, observation: Observation) -> Observation:
        """把决策的降级溯源传播到 Observation，供 hook 与终止策略观测。"""
        if decision.degraded_from is None:
            return observation
        observation.degraded_from = decision.degraded_from
        observation.extra[OBS_DEGRADED_FROM] = decision.degraded_from
        return observation
