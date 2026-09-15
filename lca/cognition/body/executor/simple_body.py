"""SimpleBody —— 通过显式 ``ActionRegistry`` 分发已获授权的行动。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from lca.cognition.body.actions.action_handlers import record_decision_made
from lca.cognition.body.executor.cursor_record import CursorRecord
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.semantic.keys import OBS_DEGRADED_FROM
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.models.core.execution.decision import Decision, Observation
from lca.contracts.models.core.execution.result import (
    ToolExecutionError,
    UnregisteredActionError,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.team.role.team import RetryPolicy
from lca.contracts.observability.cursor.loop_cursor import PhaseName
from lca.contracts.protocols import Body, SafeExecutor, ToolRegistry, TransportRegistryProtocol
from lca.contracts.protocols.act.action.action import ActionRegistryProtocol
from lca.infrastructure.component.registry import RegistryKeyError

if TYPE_CHECKING:
    from lca.runtime.session.run_session_writer import RunSessionWriter

_PERSISTENCE_FAILURE_REASON = "session_persistence_failed"


def _default_no_cache() -> Any:
    """Return a CacheConfig with caching disabled.

    ``dispatch_tool_call`` is a single-shot seam — caching is the legacy
    ToolBatchExecutor's job, not ours.
    """
    from lca.contracts.models.team.role.team import CacheConfig

    return CacheConfig(enabled=False, ttl_s=0)


def _observation_content(observation: Observation) -> str:
    """Stringify an Observation's content for ``surface/tool_result``.

    Mirrors the legacy ``commit_body_tool_execute_end`` projection: text
    payloads round-trip as strings; structured payloads JSON-encode so
    the model sees a coherent string instead of ``repr({...})``.
    """
    payload = getattr(observation, "payload", None)
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (dict, list, tuple)):
        return json.dumps(payload, ensure_ascii=False)
    return str(payload)


def _observation_error(observation: Observation) -> dict[str, Any] | None:
    """Project an Observation error to the writer's ``ToolError`` TypedDict."""
    if getattr(observation, "success", True):
        return None
    err = getattr(observation, "error", None)
    if err is None:
        return {"kind": "execution", "message": "unknown", "retryable": False}
    return {
        "kind": "execution",
        "message": str(err),
        "retryable": False,
    }


# Body 是 phase=act 执行平面;advance(phase) 是把 cursor 推到对应窗口的 SSOT。
# ADR-0169 §D1 + PR-26 task-25:phase 推进责任钉死在 SimpleBody,
# SafeExecutor / 下游 record_* 只在合法 phase 内写证据 EP。

# Body 是 phase=act 执行平面;advance(phase) 是把 cursor 推到对应窗口的 SSOT。
# ADR-0169 §D1 + PR-26 task-25:phase 推进责任钉死在 SimpleBody,
# SafeExecutor / 下游 record_* 只在合法 phase 内写证据 EP。
_ACTION_TO_PHASE: dict[str, PhaseName] = {
    ActionType.USE_TOOL.value: "act",
    ActionType.DELEGATE.value: "act",
    ActionType.HANDOFF.value: "act",
    ActionType.STOP.value: "stop",
    ActionType.ASK_HUMAN.value: "stop",
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
        writer: RunSessionWriter | None = None,
    ) -> None:
        """Create a Body from dependencies already closed by a composition seam.

        ``action_registry`` is intentionally required.  Having tools, a safe
        executor, or a transport does not itself authorize an action; only the
        compiled plan may grant that authority by constructing the registry.

        ``writer`` is the run-scoped :class:`RunSessionWriter` injected by the
        composition root. It is required by
        :meth:`dispatch_tool_call` (spec §C persist-before-execute) and
        optional for legacy :meth:`act` callers that go through the
        action registry's ToolBatchExecutor instead.
        """

        self.transport_registry = transport_registry
        self.action_registry = action_registry
        self.tool_registry = tool_registry
        self.safe_executor = safe_executor
        # v3 §9.2: OfficeWorksSealer 副作用点迁到 Body.finalize；
        # 测试可以注入替代实现。
        self._seal_office_works_fn = seal_office_works_fn
        self.writer = writer

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

    async def dispatch_tool_call(
        self,
        decision: Decision,
        state: AgentState | None = None,
    ) -> EffectReceipt:
        """Persist-before-execute a single tool call (spec §C).

        The act subgraph's responsibility for one ``use_tool`` decision:

        1. Persist ``surface/assistant_message{tool_calls=[...]}`` to the
           journal BEFORE executing the tool. The assistant row must be in
           the journal before the next LLM call sees the history.
        2. If step 1 raises (e.g. ``Session.append`` fails), return
           ``EffectReceipt(FAILED, error_code="session_persistence_failed")``
           and the tool never runs.
        3. Execute the tool via :class:`SafeExecutor`.
        4. Persist ``surface/tool_result`` linked by ``call_id``. If step 4
           raises, return the same persistence-failed receipt (the orphan
           path is closed by :meth:`RunSessionWriter.derive_messages`
           anyway, but we surface the failure explicitly).
        5. On success, return ``EffectReceipt(SUCCEEDED)``.

        ``state`` is optional — the writer is state-less and only the
        cursor advance (not relevant for this path) needs it. We accept it
        so callers can route through the same composition seam.

        This is the root-cause fix for ``run_cc39610072bf``: with
        persist-before-execute, the assistant ``tool_calls`` row is in the
        journal before the next LLM call sees the history, so an orphan
        tool row cannot precede the assistant row that declared the call.
        """
        del state
        if self.writer is None:
            raise ToolExecutionError(
                "Body.dispatch_tool_call requires a bound RunSessionWriter; "
                "construct SimpleBody(writer=...) at composition time."
            )
        if not decision.tool_calls:
            raise ToolExecutionError("dispatch_tool_call: decision has no tool_calls")
        # Single-call dispatch; the multi-call batch path is the action
        # registry's responsibility (UseToolOperation → ToolBatchExecutor).
        call = decision.tool_calls[0]
        tool = self.tool_registry.get(call.tool_name)
        if tool is None:
            raise ToolExecutionError(f"dispatch_tool_call: tool {call.tool_name!r} not registered")

        # 1. Stage the assistant(tool_calls) row in memory; the wire shape
        #    matches ``surface/assistant_message`` (id / name / arguments
        #    as JSON-encoded str, per OpenAI function-calling).
        tool_calls_payload: list[dict[str, Any]] = [
            {
                "id": call.call_id,
                "name": call.tool_name,
                "arguments": json.dumps(call.arguments, ensure_ascii=False),
            }
        ]
        # 2. Persist BEFORE executing. ``append_assistant_message`` raises
        #    ``SessionWriterUnboundError`` if the Session is unbound; any
        #    exception from ``session.append`` propagates as a persistence
        #    failure → the tool never runs.
        try:
            self.writer.append_assistant_message(
                turn=0,
                step=0,
                role="assistant",
                content=None,
                tool_calls=tool_calls_payload,  # type: ignore[arg-type]
                usage=None,
            )
        except Exception:
            return EffectReceipt(
                invocation_id=call.call_id,
                outcome=EffectOutcome.FAILED,
                idempotency_key=f"{call.call_id}:persist_assistant",
                provider="body.dispatch_tool_call",
                error_code=_PERSISTENCE_FAILURE_REASON,
            )

        # 3. Now execute the tool. The executor persists the tool_result
        #    via ``commit_body_tool_execute_end`` (Task 4 migration to
        #    ``RunSessionWriter.append_tool_result``); we also append
        #    explicitly here so a missing migration in some other executor
        #    does not leave the journal without the result row.
        observation = await self.safe_executor.execute(
            tool,
            dict(call.arguments),
            retry_policy=RetryPolicy(max_retries=0),
            cache_config=_default_no_cache(),
            invocation_id=call.call_id,
        )

        # 4. Persist the tool result linked by call_id. ``meta`` carries
        #    tool_name for downstream consumers; orphan-drop at
        #    ``derive_messages`` will drop the result if the assistant
        #    row never landed (defence in depth).
        try:
            self.writer.append_tool_result(
                turn=0,
                step=0,
                call_id=call.call_id,
                content=_observation_content(observation),
                error=_observation_error(observation),
                meta={"tool_name": call.tool_name},
            )
        except Exception:
            return EffectReceipt(
                invocation_id=call.call_id,
                outcome=EffectOutcome.FAILED,
                idempotency_key=f"{call.call_id}:persist_result",
                provider="body.dispatch_tool_call",
                error_code=_PERSISTENCE_FAILURE_REASON,
            )

        # 5. Success path.
        if observation.success:
            return EffectReceipt(
                invocation_id=call.call_id,
                outcome=EffectOutcome.SUCCEEDED,
                idempotency_key=call.call_id,
                provider="body.dispatch_tool_call",
            )
        return EffectReceipt(
            invocation_id=call.call_id,
            outcome=EffectOutcome.FAILED,
            idempotency_key=call.call_id,
            provider="body.dispatch_tool_call",
            error_code="tool_execution_failed",
        )

    @staticmethod
    def _advance_cursor_for_action(action_type: str) -> None:
        """Bound cursor 已就位 → 按 action_type 推进 phase;否则 no-op (R2).

        best-effort:取不到 cursor 或 advance 抛 CursorError → warning + 继续。

        ``action_type`` 是 ``Decision.action_type`` 的字符串值
        (contracts/models/core/decision.py:69),不是 ``ActionType`` enum。
        字典 key 用 ``.value`` 是为了字典查表类型诚实,与调用者传入形态一致。
        """
        target = _ACTION_TO_PHASE.get(action_type)
        if target is None:
            return
        CursorRecord.try_advance(target, action_type=action_type)

    async def finalize(self, observation: Observation, state: AgentState) -> None:
        """手平面 finalize（v3 §9.2：OfficeWorksSealer 迁移点）。

        当前 turn 即将关闭（RESPOND / STOP / ASK_HUMAN）或到达预算上限时
        触发；调用方在声明式 stop phase 中调用。
        """
        from lca.contracts.models.core.policy.budget import TERMINAL_RESERVE_STEPS

        last_decision = state.history[-1].decision if state.history else None
        # ``Decision.action_type`` 是 str(contracts/models/core/decision.py:69),
        # 与 ``ActionType(str, Enum)`` 字面量等价;这里用 enum 表达 closure set
        # 只是为了 IDE 跳转 / 重构追踪,运行时比较仍然走 str 值。
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
