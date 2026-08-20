"""内置 Action 实现 —— 从 SimpleBody 提取的独立策略类。

每种 action_type 对应一个独立 Operation，彼此零依赖、零共享可变状态。
新增行动能力 = ActionCatalog 加一条 spec + 本模块一个 Operation + 注册。

DELEGATE/HANDOFF 成员调用统一走 ``send_and_wait``（与 strategy 同端口）。
委派叙事由 transport 边界统一发射；决策事实（DecisionMade）与 board
收口综合（SynthesisCompleted）在本模块发射（ADR-0037 journal）。
"""

from __future__ import annotations

import asyncio
from typing import Any

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
    OBS_TOOL_RESULTS,
)
from lca.contracts.models.core.budget import (
    DEFAULT_DELEGATION_TIMEOUT_S,
    resolve_delegation_timeout_s,
)
from lca.contracts.models.core.decision import Decision, DelegationSpec, Observation, ToolCall
from lca.contracts.models.core.lifecycle import AgentCard
from lca.contracts.models.core.result import ToolExecutionError
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import DecisionMade, SynthesisCompleted
from lca.contracts.models.team.consultation import SynthesisMethod, usable_outcomes
from lca.contracts.models.team.delegation_context import delegator_scope
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy
from lca.contracts.protocols import (
    AgentTransport,
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.action import Action
from lca.layer0_infra.observability import record
from lca.layer0_infra.transport.invocation import handoff_task_traced, send_and_wait
from lca.layer1_cognitive.body.delegation_cache import (
    cached_delegation_observation,
    tag_delegation_extra,
)
from lca.layer1_cognitive.body.tool_wire_gate import tool_wire_block_observation
from lca.layer1_cognitive.member_status.consult_policy import (
    classify_synthesis,
    run_wall_clock_remaining_s,
)
from lca.layer1_cognitive.member_status.required_action import compute_required_action
from lca.layer1_cognitive.member_status.tracking import (
    duty_board,
    duty_consult,
    record_delegation_return,
)

_ERR_DEADLINE_EXPIRED = "delegate 超时(deadline 已过期)"
_ERR_TIMEOUT = "delegate 超时"


def record_decision_made(decision: Decision, state: AgentState) -> None:
    """发射决策事实（所有 action_type 统一入口，供 InsightEngine 循环检测）。"""
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


class UseToolOperation(Action):
    """处理 use_tool 动作：wire 闸门 → 查找工具 → 权限校验 → 执行。

    ADR-0047：``tool_wire_status`` 为 incomplete/invalid 时**禁止执行**，
    返回 ``Observation(success=False)`` 回灌 loop（不抛、不 respond 收口）。
    """

    def __init__(self, tool_registry: ToolRegistry, safe_executor: SafeExecutor) -> None:
        self._tool_registry = tool_registry
        self._safe_executor = safe_executor

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        if not decision.tool_calls:
            raise ToolExecutionError("use_tool 需要至少一个 tool_call")
        wire_block = tool_wire_block_observation(decision)
        if wire_block is not None:
            return wire_block

        # Resolve all tools up front — fail fast before launching any execution.
        resolved = []
        for tc in decision.tool_calls:
            tool = self._tool_registry.get(tc.tool_name)
            if tool is None:
                raise ToolExecutionError(f"未注册工具: {tc.tool_name}")
            resolved.append((tc, tool))

        if len(resolved) == 1:
            tc, tool = resolved[0]
            observation = await self._safe_executor.execute(
                tool,
                tc.arguments,
                RetryPolicy(),
                CacheConfig(),
                invocation_id=tc.call_id or "",
            )
            extra = dict(observation.extra or {})
            extra.setdefault(OBS_RESULT_KIND, MemoryRecordKind.TOOL_RESULT)
            observation.extra = extra
            return observation

        # Parallel execution — asyncio.gather is the Python equivalent of
        # LobeHub's Promise.all for concurrent tool calls.
        observations = await asyncio.gather(
            *[
                self._safe_executor.execute(
                    tool,
                    tc.arguments,
                    RetryPolicy(),
                    CacheConfig(),
                    invocation_id=tc.call_id or "",
                )
                for tc, tool in resolved
            ]
        )
        return _combine_tool_observations(observations, decision.tool_calls)


def _combine_tool_observations(
    observations: tuple[Observation, ...] | list[Observation],
    tool_calls: list[ToolCall],
) -> Observation:
    """Package parallel tool results into a single Observation.

    Individual observations are preserved in ``extra[OBS_TOOL_RESULTS]``
    so ``build_tool_history`` can emit one assistant+tool message pair
    per tool call — matching OpenAI / LobeHub native wire format.
    """
    observations = list(observations)
    all_ok = all(obs.success for obs in observations)
    errors = [
        e for e in (obs.error for obs in observations if not obs.success) if e
    ]
    extra: dict[str, Any] = {
        OBS_RESULT_KIND: MemoryRecordKind.TOOL_RESULT,
        OBS_TOOL_RESULTS: [
            {"call_id": tc.call_id, "tool_name": tc.tool_name, "observation": obs}
            for tc, obs in zip(tool_calls, observations, strict=True)
        ],
    }
    payload = {
        "tool_count": len(observations),
        "all_success": all_ok,
    }
    return Observation(
        observation_id=new_id("obs"),
        success=all_ok,
        payload=payload,
        error="; ".join(errors) if errors else "",
        extra=extra,
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
            return await self._execute_one(specs[0], state)
        return await self._execute_many(specs, state)

    async def _execute_one(self, spec: DelegationSpec, state: AgentState) -> Observation:
        cached = cached_delegation_observation(spec, state)
        if cached is not None:
            return cached
        observation = await self._invoke(spec, state)
        self._record_return(spec, observation, state)
        return tag_delegation_extra(observation, spec)

    async def _execute_many(self, specs: list[DelegationSpec], state: AgentState) -> Observation:
        returns: dict[int, Observation] = {}
        pending: list[tuple[int, DelegationSpec]] = []
        for index, spec in enumerate(specs):
            cached = cached_delegation_observation(spec, state)
            if cached is not None:
                returns[index] = cached
            else:
                pending.append((index, spec))
        fresh = await asyncio.gather(*[self._invoke(spec, state) for _, spec in pending])
        for (index, spec), observation in zip(pending, fresh, strict=True):
            self._record_return(spec, observation, state)
            returns[index] = observation
        observations = [returns[index] for index in range(len(specs))]

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
        transport, agent_card = self._resolve_target(spec, state)
        timeout_s = resolve_spec_timeout_s(spec, state)
        if timeout_s <= 0:
            return _timeout_observation(_ERR_DEADLINE_EXPIRED)
        try:
            with delegator_scope(state.agent_role):
                observation = await send_and_wait(
                    transport,
                    agent_card,
                    spec.subtask,
                    spec.context_refs,
                    timeout_s=timeout_s,
                )
        except TimeoutError:
            return _timeout_observation(_ERR_TIMEOUT)
        # transport 已 harvest 时直接透传（含 partial payload）
        return observation

    def _resolve_target(
        self, spec: DelegationSpec, state: AgentState
    ) -> tuple[AgentTransport, AgentCard | str]:
        del state
        transport = self._transport_registry.resolve(spec.protocol)
        agent_card: AgentCard | str | None = (
            spec.target_agent_card or spec.target_agent_id or spec.target_role
        )
        if agent_card is None:
            raise ToolExecutionError("delegate 动作缺少目标（agent_card / agent_id / role 均为空）")
        return transport, agent_card


class HandoffOperation(Action):
    """处理 handoff 动作：非阻塞控制权移交，发完即返回（不等待结果）。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        specs = list(decision.delegations)
        if not specs:
            raise ToolExecutionError("handoff 动作缺少 delegations 规格")
        spec = specs[0]
        transport = self._transport_registry.resolve(spec.protocol)
        agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
        if agent_card is None:
            raise ToolExecutionError("handoff 动作缺少目标（agent_card / agent_id / role 均为空）")
        with delegator_scope(state.agent_role):
            task_id = await handoff_task_traced(
                transport, agent_card, spec.subtask, spec.context_refs
            )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=f"handoff to {spec.target_role or spec.target_agent_id}",
            extra={OBS_TASK_ID: task_id, OBS_HANDOFF: True},
        )
