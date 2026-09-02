"""SimpleBody —— 通过显式 ``ActionRegistry`` 分发已获授权的行动。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from lca.cognition.body.action_handlers import record_decision_made
from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.semantic_keys import OBS_DEGRADED_FROM
from lca.contracts.models.core.decision import Decision, Observation
from lca.contracts.models.core.result import UnregisteredActionError
from lca.contracts.models.core.state import AgentState
from lca.contracts.observability.loop_cursor import CursorError, PhaseName
from lca.contracts.protocols import Body, SafeExecutor, ToolRegistry, TransportRegistryProtocol
from lca.contracts.protocols.act.action import ActionRegistryProtocol
from lca.infrastructure.component_registry import RegistryKeyError

_log = structlog.get_logger(__name__)

# Body 是 phase=act 执行平面;advance(phase) 是把 cursor 推到对应窗口的 SSOT。
# ADR-0169 §D1 + PR-26 task-25:phase 推进责任钉死在 SimpleBody,
# SafeExecutor / 下游 record_* 只在合法 phase 内写证据 EP。
_ACTION_TO_PHASE: dict[ActionType, PhaseName] = {
    ActionType.USE_TOOL: "act",
    ActionType.DELEGATE: "act",
    ActionType.HANDOFF: "act",
    ActionType.STOP: "stop",
    ActionType.ASK_HUMAN: "stop",
    # RESPOND: think phase 内 emit response;不进 act/stop。
}


class SimpleBody(Body):
    """Default ``Body`` implementation that dispatches a compiled action registry.

    ``BodyComposer`` is the composition seam that derives the registry from a
    compiled ``ActionAuthorityPlan``.  This class deliberately consumes that
    completed registry only: it must not infer a scope, create default actions,
    or turn dependencies into executable authority.  Tests use the same
    explicit construction rule through ``tests.support.action_authority``.

    契约不变量（v3 §5.3 / §9.1 / PR6 / PR10 + ADR-0169 PR-26）：
    - ``act`` 只分发已经由计划授权并注册的 ``action_type``。
    - ``act`` 入口按 ``decision.action_type`` 推进 cursor 到 act/stop;
      Cursor 是 phase 推进 SSOT(ADR-0169 PR-26 task-25)。
    - ``CommandEnvelope`` 是声明式执行链唯一的效果授权入口；Body 不再补造
      旧的 ``ExecutionEnvelope``。
    - 协议边界派生事件：``ActionDegraded`` 由 ``ProjectionHost`` 或
      ``cursor.record_*(...)`` 派生(ADR-0169 §D8 / D1);Body 不再走
      ``_derive_action_degraded`` hook(ADR-0169 §D9 删除)。
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

        Degradation emission (v3 §4.4 + §10) is no longer derived via the
        legacy degradation-emission hook (ADR-0169 §D9 deletion:
        both derivation helpers are removed; event emission re-routed
        through ``cursor.record_*(...)`` or ProjectionHost). Body still
        propagates the marker via
        :meth:`_propagate_degradation` so downstream subscribers can
        observe ``observation.degraded_from``.

        phase 推进责任(ADR-0169 PR-26 task-25):本方法按 ``decision.action_type``
        决定 cursor 推进到 act/stop;Cursor 校验失败(cursor 已 closed/halted 或
        非法转移)降级 warning,不让单 decision 失败变 session RuntimeError。
        """

        self._advance_cursor_for_action(decision.action_type)
        try:
            handler = self.action_registry.resolve(decision.action_type)
        except (KeyError, RegistryKeyError) as exc:
            raise UnregisteredActionError(decision.action_type) from exc
        record_decision_made(decision, state)
        observation = await handler.execute(decision, state)
        return self._propagate_degradation(decision, observation)

    @staticmethod
    def _advance_cursor_for_action(action_type: ActionType) -> None:
        """Bound cursor 已就位 → 按 action_type 推进 phase;否则 no-op。

        best-effort:取不到 cursor 或 advance 抛 CursorError → warning + 继续。
        """
        target = _ACTION_TO_PHASE.get(action_type)
        if target is None:
            return
        from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
            get_current_cursor,
        )

        cursor = get_current_cursor()
        if cursor is None:
            return
        try:
            cursor.advance(target)
        except CursorError as exc:
            _log.warning(
                "body_advance_cursor_failed",
                action_type=action_type.value,
                target_phase=target,
                current_phase=cursor.snapshot.phase,
                error=str(exc),
            )

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

        ADR-0169 PR-26:``ActionDegraded`` 不再由 ``_derive_action_degraded``
        派生(hook 已删除);下游消费者走 cursor.record_*(...) 或 ProjectionHost
        读取 ``observation.degraded_from`` / ``observation.extra[OBS_DEGRADED_FROM]``。
        Body 只负责在 observation 上携带 marker,不再 emit。
        """
        if decision.degraded_from is None:
            return observation
        observation.degraded_from = decision.degraded_from
        observation.extra[OBS_DEGRADED_FROM] = decision.degraded_from
        return observation
