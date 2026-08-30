"""SimpleBody —— 通过显式 ``ActionRegistry`` 分发已获授权的行动。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.semantic_keys import OBS_DEGRADED_FROM
from lca.contracts.models.core.decision import Decision, Observation
from lca.contracts.models.core.result import UnregisteredActionError
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import Body, SafeExecutor, ToolRegistry, TransportRegistryProtocol
from lca.contracts.protocols.action import ActionRegistryProtocol
from lca.infrastructure.component_registry import RegistryKeyError
from lca.layer1_cognitive.body.action_handlers import record_decision_made


class SimpleBody(Body):
    """Default ``Body`` implementation that dispatches a compiled action registry.

    ``BodyComposer`` is the composition seam that derives the registry from a
    compiled ``ActionAuthorityPlan``.  This class deliberately consumes that
    completed registry only: it must not infer a scope, create default actions,
    or turn dependencies into executable authority.  Tests use the same
    explicit construction rule through ``tests.support.action_authority``.

    契约不变量（v3 §5.3 / §9.1 / PR6 / PR10）：
    - ``act`` 只分发已经由计划授权并注册的 ``action_type``。
    - ``CommandEnvelope`` 是声明式执行链唯一的效果授权入口；Body 不再补造
      旧的 ``ExecutionEnvelope``。
    - 协议边界派生事件：``ActionDegraded`` 在 ``act`` 末尾直接 ``record()``，
      不再走 hook 派生（v3 §4.4）。
    - ``finalize`` 是 Body finalize 钩子，OfficeWorksSealer 等手平面副作用
      从这里调用；不在 ``act`` 内部。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistryProtocol,
        action_registry: ActionRegistryProtocol,
        *,
        seal_office_works_fn: Callable[..., Any] | None = None,
    ) -> None:
        """Create a Body from dependencies already closed by a composition seam.

        ``action_registry`` is intentionally required.  Having tools, a safe
        executor, or a transport does not itself authorize an action; only the
        compiled plan may grant that authority by constructing the registry.
        """

        self.transport_registry = transport_registry
        self.action_registry = action_registry
        self.tool_registry = tool_registry
        self.safe_executor = safe_executor
        # v3 §9.2: OfficeWorksSealer 副作用点迁到 Body.finalize；
        # 测试可以注入替代实现。
        self._seal_office_works_fn = seal_office_works_fn

    async def act(self, decision: Decision, state: AgentState) -> Observation:
        """Execute a decision through its already-authorized action handler.

        Degradation emission (v3 §4.4 + §10) lives in
        :func:`lca.layer2_runtime.event_emission._derive_action_degraded`,
        which subscribes to ``HookEvent.POST_ACT`` and reads
        ``observation.degraded_from`` that we surface here via
        :meth:`_propagate_degradation`. Body never emits ``ActionDegraded``
        directly.
        """

        try:
            handler = self.action_registry.resolve(decision.action_type)
        except (KeyError, RegistryKeyError) as exc:
            raise UnregisteredActionError(decision.action_type) from exc
        record_decision_made(decision, state)
        observation = await handler.execute(decision, state)
        return self._propagate_degradation(decision, observation)

    async def finalize(self, observation: Observation, state: AgentState) -> None:
        """手平面 finalize（v3 §9.2：OfficeWorksSealer 迁移点）。

        当前 turn 即将关闭（RESPOND / STOP / ASK_HUMAN）或到达预算上限时
        触发；调用方在声明式 stop phase 中调用。
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

    @staticmethod
    def _propagate_degradation(decision: Decision, observation: Observation) -> Observation:
        """Surface the degradation marker on ``Observation`` for downstream emission.

        The actual ``ActionDegraded`` journal event is emitted by
        :func:`lca.layer2_runtime.event_emission._derive_action_degraded`
        via the ``POST_ACT`` hook (v3 §4.4 + §10). Body is responsible only
        for carrying the marker on the observation; it does not emit.
        """
        if decision.degraded_from is None:
            return observation
        observation.degraded_from = decision.degraded_from
        observation.extra[OBS_DEGRADED_FROM] = decision.degraded_from
        return observation
