"""内置 Action 实现 —— 从 SimpleBody 提取的独立策略类。

每种 action_type 对应一个独立 Operation，彼此零依赖、零共享可变状态。
新增行动能力 = ActionCatalog 加一条 spec + 本模块一个 Operation + 注册。

DELEGATE/HANDOFF 成员调用统一走 ``send_and_wait``（与 strategy 同端口）。
委派叙事由 transport 边界统一发射；决策事实（DecisionMade）与 board
收口综合（SynthesisCompleted）在本模块发射（ADR-0037 journal）。
"""

from __future__ import annotations

import asyncio

from lca.cognition.body.delegation_cache import (
    cached_delegation_observation,
    tag_delegation_extra,
)
from lca.cognition.body.delegation_target import resolve_delegation_target
from lca.cognition.body.tool_batch_executor import ToolBatchExecutor
from lca.cognition.body.tool_wire_gate import tool_wire_block_observation
from lca.cognition.member_status.consult_policy import (
    classify_synthesis,
    run_wall_clock_remaining_s,
)
from lca.cognition.member_status.required_action import compute_required_action
from lca.cognition.member_status.tracking import (
    duty_board,
    duty_consult,
    record_delegation_return,
)
from lca.cognition.transport_envelope import delegate_via_envelope, handoff_via_envelope
from lca.contracts.atoms.enums import MemoryRecordKind
from lca.contracts.atoms.ids import new_id, remaining_seconds
from lca.contracts.atoms.semantic_keys import (
    COMPLETION_EMPTY,
    COMPLETION_PARTIAL,
    FAILURE_KIND,
    FAILURE_KIND_TRANSIENT,
    OBS_COMPLETION_QUALITY,
    OBS_HANDOFF,
    OBS_MEMBER_RESULTS,
    OBS_MEMBER_SUBTASKS,
    OBS_RESULT_KIND,
    OBS_TASK_ID,
    OBS_TASK_IDS,
)
from lca.contracts.models.core.budget import (
    DEFAULT_DELEGATION_TIMEOUT_S,
    resolve_delegation_timeout_s,
)
from lca.contracts.models.core.decision import Decision, DelegationSpec, Observation
from lca.contracts.models.core.result import ToolExecutionError
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import DecisionMade, SynthesisCompleted
from lca.contracts.models.team.consultation import SynthesisMethod, usable_outcomes
from lca.contracts.models.team.delegation_context import delegator_scope
from lca.contracts.protocols import (
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.act.action import Action
from lca.contracts.protocols.act.command_envelope import command_envelope_to_dict
from lca.contracts.protocols.act.tool_batch_execution import ToolBatchExecutionPolicy
from lca.infrastructure.observability import record
from lca.plugins.observability.spine.reflectors import body_llm as _body_llm_reflector

_ERR_DEADLINE_EXPIRED = "delegate 超时(deadline 已过期)"
_ERR_TIMEOUT = "delegate 超时"


def record_decision_made(decision: Decision, state: AgentState) -> None:
    """发射决策事实；TraceInspector 可从账本按需分析动作模式。"""
    delegate_target = ""
    delegate_count = 0
    if decision.delegations:
        first = decision.delegations[0]
        delegate_target = first.target_role or first.target_agent_id or ""
        delegate_count = len(decision.delegations) if len(decision.delegations) > 1 else 0
    tool_name = decision.tool_calls[0].tool_name if decision.tool_calls else ""
    record(
        DecisionMade(
            step=state.step,
            action_type=decision.action_type,
            rationale_preview=decision.rationale,
            delegate_target=delegate_target,
            delegate_count=delegate_count,
            tool_name=tool_name,
            confidence=decision.confidence,
            # 规范正文：已经过 DecisionParser 形状归一（ADR-0045）
            response_text=decision.response_text or "",
        )
    )


def _timeout_observation(error: str, *, payload: object = None) -> Observation:
    quality = COMPLETION_PARTIAL if payload else COMPLETION_EMPTY
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=payload,
        error=error,
        extra={
            FAILURE_KIND: FAILURE_KIND_TRANSIENT,
            OBS_COMPLETION_QUALITY: quality,
        },
    )


def resolve_spec_timeout_s(spec: DelegationSpec, state: AgentState) -> float:
    """委派超时唯一解析入口（ADR-0049）：spec > deadline > run 剩余 ∩ 默认。"""
    deadline_rem: float | None = None
    if spec.deadline is not None:
        deadline_rem = remaining_seconds(spec.deadline)
    return resolve_delegation_timeout_s(
        explicit_timeout_s=spec.timeout_s,
        deadline_remaining_s=deadline_rem,
        run_wall_clock_remaining_s=run_wall_clock_remaining_s(state.budget),
        default_timeout_s=DEFAULT_DELEGATION_TIMEOUT_S,
    )


class RespondOperation(Action):
    """处理 respond 动作：直接返回文本响应。

    board/consult 收口可见化：lead 在全部必问成员终态后产出终版响应时，
    record ``SynthesisCompleted``，method 按证据完备度命名（ADR-0049）。
    """

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        self._record_synthesis(decision, state)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=decision.response_text,
            extra={OBS_RESULT_KIND: MemoryRecordKind.RESPONSE},
        )

    @staticmethod
    def _record_synthesis(decision: Decision, state: AgentState) -> None:
        board = duty_board(state)
        if board is None:
            return
        if compute_required_action(board).kind != "may_respond":
            return
        duty = duty_consult(state)
        if duty is not None:
            method = classify_synthesis(board, duty.outcomes)
            candidate_count = len(usable_outcomes(duty.outcomes))
        else:
            method = SynthesisMethod.FULL
            candidate_count = len(board.required_roles)
        record(
            SynthesisCompleted(
                method=method.value,
                candidate_count=candidate_count,
                output_text=decision.response_text or "",
            )
        )


class TerminalOperation(Action):
    """Complete a terminal decision without creating a world effect."""

    async def execute(self, decision: Decision, _state: AgentState) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=decision.response_text,
            extra={OBS_RESULT_KIND: MemoryRecordKind.RESPONSE},
        )


class AskHumanOperation(TerminalOperation):
    """Expose an explicit human-input observation for the terminal action."""


class UseToolOperation(Action):
    """处理 use_tool 动作：wire 闸门 → 查找工具 → 权限校验 → 执行。

    ADR-0047：``tool_wire_status`` 为 incomplete/invalid 时**禁止执行**，
    返回 ``Observation(success=False)`` 回灌 loop（不抛、不 respond 收口）。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        *,
        batch_execution_policy: ToolBatchExecutionPolicy,
    ) -> None:
        self._batch_executor = ToolBatchExecutor(
            tool_registry,
            safe_executor,
            policy=batch_execution_policy,
        )

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        if not decision.tool_calls:
            raise ToolExecutionError("use_tool 需要至少一个 tool_call")
        wire_block = tool_wire_block_observation(decision)
        if wire_block is not None:
            return wire_block

        # PR-3.3: emit body.tool.execute.start/end at the action-handler layer
        # so the spine sees one ``start``/``end`` pair per ``use_tool`` decision
        # (regardless of batch size), bracketing the batch dispatch. The
        # individual ``tool.execute(args)`` call inside SafeExecutor also
        # emits its own per-call pair; this higher-level pair carries the
        # tool-name list in the payload so consumers can join them by
        # ``decision_id`` and parent_span_id.
        tool_names = [tc.tool_name for tc in decision.tool_calls]
        _body_llm_reflector.emit_body_tool_execute_start(
            tool_name=",".join(tool_names) or "use_tool",
            invocation_id=decision.decision_id or "",
            attempt=1,
        )
        try:
            return await self._batch_executor.execute(decision.tool_calls)
        finally:
            _body_llm_reflector.emit_body_tool_execute_end(
                tool_name=",".join(tool_names) or "use_tool",
                invocation_id=decision.decision_id or "",
                attempt=1,
                outcome="success",
            )


class DelegateOperation(Action):
    """处理 delegate 动作：单目标阻塞或 multi fan-out 并行等待。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        specs = list(decision.delegations)
        if not specs:
            raise ToolExecutionError(f"{decision.action_type} 动作缺少 delegations 规格")
        if len(specs) == 1:
            observation = await self._resolve_observation(specs[0], state)
            return tag_delegation_extra(observation, specs[0])
        observations = await asyncio.gather(
            *[self._resolve_observation(spec, state) for spec in specs]
        )
        return self._aggregate_observations(specs, list(observations))

    async def _resolve_observation(self, spec: DelegationSpec, state: AgentState) -> Observation:
        """Cache → invoke → record seam shared by single and multi paths.

        Single-target delegation reuses this directly; multi-target fans the
        same call out via ``asyncio.gather`` and aggregates the observations
        in :meth:`_aggregate_observations`. Keeping cache bookkeeping and
        invoke semantics in one place prevents the two paths from drifting.
        """
        cached = cached_delegation_observation(spec, state)
        if cached is not None:
            return cached
        observation = await self._invoke(spec, state)
        self._record_return(spec, observation, state)
        return observation

    def _aggregate_observations(
        self, specs: list[DelegationSpec], observations: list[Observation]
    ) -> Observation:
        """Fold N per-spec observations into one multi-delegate Observation."""

        member_payload: dict[str, object] = {}
        member_subtasks: dict[str, object] = {}
        task_ids: list[str] = []
        for spec, obs in zip(specs, observations, strict=True):
            key = spec.target_role or spec.target_agent_id or obs.observation_id
            # 失败但有 partial 时保留证据，不把 error 字符串盖住正文（ADR-0049）
            if obs.success or obs.payload is not None:
                member_payload[str(key)] = obs.payload
            else:
                member_payload[str(key)] = obs.error
            member_subtasks[str(key)] = spec.subtask
            task_ids.append(str(obs.extra.get(OBS_TASK_ID, obs.observation_id)))

        all_ok = all(o.success for o in observations)
        return Observation(
            observation_id=new_id("obs"),
            success=all_ok,
            payload=member_payload,
            error=None if all_ok else "one or more delegates failed",
            extra={
                OBS_TASK_IDS: task_ids,
                OBS_MEMBER_RESULTS: member_payload,
                OBS_MEMBER_SUBTASKS: member_subtasks,
                OBS_RESULT_KIND: MemoryRecordKind.DELEGATION_RESULT,
            },
        )

    def _record_return(
        self, spec: DelegationSpec, observation: Observation, state: AgentState
    ) -> None:
        record_delegation_return(state, spec, observation)

    async def _invoke(self, spec: DelegationSpec, state: AgentState) -> Observation:
        transport, agent_card = resolve_delegation_target(spec, self._transport_registry)
        timeout_s = resolve_spec_timeout_s(spec, state)
        if timeout_s <= 0:
            return _timeout_observation(_ERR_DEADLINE_EXPIRED)
        try:
            with delegator_scope(state.agent_role):
                observation, envelope = await delegate_via_envelope(
                    transport,
                    agent_card,
                    spec.subtask,
                    spec.context_refs,
                    timeout_s=timeout_s,
                    decision_ref=spec.target_agent_id or spec.target_role or "delegate",
                    protocol=spec.protocol,
                )
                observation.extra = dict(observation.extra or {})
                observation.extra["command_envelope"] = command_envelope_to_dict(envelope)
        except TimeoutError:
            return _timeout_observation(_ERR_TIMEOUT)
        # transport 已 harvest 时直接透传（含 partial payload）
        return observation


class HandoffOperation(Action):
    """处理 handoff 动作：非阻塞控制权移交，发完即返回（不等待结果）。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        specs = list(decision.delegations)
        if not specs:
            raise ToolExecutionError("handoff 动作缺少 delegations 规格")
        spec = specs[0]
        transport, agent_card = resolve_delegation_target(spec, self._transport_registry)
        with delegator_scope(state.agent_role):
            task_id, envelope = await handoff_via_envelope(
                transport,
                agent_card,
                spec.subtask,
                spec.context_refs,
                decision_ref=spec.target_agent_id or spec.target_role or "handoff",
                protocol=spec.protocol,
            )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=f"handoff to {spec.target_role or spec.target_agent_id}",
            extra={
                OBS_TASK_ID: task_id,
                OBS_HANDOFF: True,
                "command_envelope": command_envelope_to_dict(envelope),
            },
        )
