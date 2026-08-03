"""内置 Action 实现 —— 从 SimpleBody 提取的独立策略类。

每种 action_type 对应一个独立 Operation，彼此零依赖、零共享可变状态。
新增行动能力 = ActionCatalog 加一条 spec + 本模块一个 Operation + 注册。
"""

from __future__ import annotations

import asyncio

from lca.contracts.action import Action
from lca.contracts.decision import Decision, DelegationSpec, Observation, iter_delegation_specs
from lca.contracts.delegation_context import delegator_scope
from lca.contracts.ids import new_id, remaining_seconds
from lca.contracts.protocols import (
    AgentTransport,
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy
from lca.contracts.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_TRANSIENT,
    OBS_HANDOFF,
    OBS_MEMBER_RESULTS,
    OBS_TASK_ID,
    OBS_TASK_IDS,
)
from lca.contracts.state import AgentState
from lca.layer1_cognitive.member_status.tracking import (
    record_routing_assignment,
    update_member_status_for_spec,
)

_DEFAULT_DELEGATE_TIMEOUT_S = 30.0


class RespondOperation(Action):
    """处理 respond 动作：直接返回文本响应。"""

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=decision.response_text,
        )


class UseToolOperation(Action):
    """处理 use_tool 动作：查找工具 → 权限校验 → 执行。"""

    def __init__(self, tool_registry: ToolRegistry, safe_executor: SafeExecutor) -> None:
        self._tool_registry = tool_registry
        self._safe_executor = safe_executor

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        if not decision.tool_calls:
            raise ToolExecutionError("use_tool 需要至少一个 tool_call")
        tc = decision.tool_calls[0]
        tool = self._tool_registry.get(tc.tool_name)
        if tool is None:
            raise ToolExecutionError(f"未注册工具: {tc.tool_name}")
        return await self._safe_executor.execute(tool, tc.arguments, RetryPolicy(), CacheConfig())


class DelegateOperation(Action):
    """处理 delegate 动作：单目标阻塞或 multi fan-out 并行等待。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        specs = iter_delegation_specs(decision)
        if not specs:
            raise ToolExecutionError(f"{decision.action_type} 动作缺少 delegate 规格")
        if len(specs) == 1:
            return await self._execute_one(specs[0], state)
        return await self._execute_many(specs, state)

    async def _execute_one(self, spec: DelegationSpec, state: AgentState) -> Observation:
        transport, task_id = await self._send_spec(spec, state)
        timeout_s = self._timeout_for(spec)
        if timeout_s <= 0:
            observation = Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"delegate 超时(deadline 已过期): task_id={task_id}",
                extra={OBS_TASK_ID: task_id, FAILURE_KIND: FAILURE_KIND_TRANSIENT},
            )
            update_member_status_for_spec(state, spec, observation)
            record_routing_assignment(state, spec)
            return observation

        observation = await self._wait_for_result(transport, task_id, timeout_s)
        update_member_status_for_spec(state, spec, observation)
        record_routing_assignment(state, spec)
        observation.extra[OBS_TASK_ID] = task_id
        return observation

    async def _execute_many(self, specs: list[DelegationSpec], state: AgentState) -> Observation:
        """Fan-out: send all, wait all, settle board per role."""
        sent: list[tuple[DelegationSpec, AgentTransport, str, float]] = []
        for spec in specs:
            transport, task_id = await self._send_spec(spec, state)
            sent.append((spec, transport, task_id, self._timeout_for(spec)))

        async def _one(
            spec: DelegationSpec, transport: AgentTransport, task_id: str, timeout_s: float
        ) -> Observation:
            if timeout_s <= 0:
                return Observation(
                    observation_id=new_id("obs"),
                    success=False,
                    payload=None,
                    error=f"delegate 超时(deadline 已过期): task_id={task_id}",
                    extra={OBS_TASK_ID: task_id, FAILURE_KIND: FAILURE_KIND_TRANSIENT},
                )
            obs = await self._wait_for_result(transport, task_id, timeout_s)
            obs.extra[OBS_TASK_ID] = task_id
            return obs

        observations = await asyncio.gather(
            *[_one(spec, tr, tid, to) for spec, tr, tid, to in sent]
        )
        member_payload: dict[str, object] = {}
        task_ids: list[str] = []
        for (spec, _tr, task_id, _to), obs in zip(sent, observations, strict=True):
            update_member_status_for_spec(state, spec, obs)
            record_routing_assignment(state, spec)
            key = spec.target_role or spec.target_agent_id or task_id
            member_payload[str(key)] = obs.payload if obs.success else obs.error
            task_ids.append(task_id)

        all_ok = all(o.success for o in observations)
        return Observation(
            observation_id=new_id("obs"),
            success=all_ok,
            payload=member_payload,
            error=None if all_ok else "one or more delegates failed",
            extra={OBS_TASK_IDS: task_ids, OBS_MEMBER_RESULTS: member_payload},
        )

    @staticmethod
    def _timeout_for(spec: DelegationSpec) -> float:
        if spec.deadline:
            return remaining_seconds(spec.deadline)
        return _DEFAULT_DELEGATE_TIMEOUT_S

    async def _wait_for_result(
        self,
        transport: AgentTransport,
        task_id: str,
        timeout_s: float,
    ) -> Observation:
        try:
            return await transport.wait_result(task_id, timeout_s)
        except TimeoutError:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"delegate 超时: task_id={task_id}",
                extra={OBS_TASK_ID: task_id, FAILURE_KIND: FAILURE_KIND_TRANSIENT},
            )

    async def _send_spec(
        self, spec: DelegationSpec, state: AgentState
    ) -> tuple[AgentTransport, str]:
        transport = self._transport_registry.resolve(spec.protocol)
        agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
        if agent_card is None:
            raise ToolExecutionError("delegate 动作缺少目标（agent_card / agent_id / role 均为空）")
        with delegator_scope(state.agent_role):
            task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        return transport, task_id


class HandoffOperation(Action):
    """处理 handoff 动作：非阻塞控制权移交，发完即返回。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        specs = iter_delegation_specs(decision)
        if not specs:
            raise ToolExecutionError("handoff 动作缺少 delegate 规格")
        spec = specs[0]
        transport = self._transport_registry.resolve(spec.protocol)
        agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
        if agent_card is None:
            raise ToolExecutionError("handoff 动作缺少目标（agent_card / agent_id / role 均为空）")
        with delegator_scope(state.agent_role):
            task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=f"handoff to {spec.target_role or spec.target_agent_id}",
            extra={OBS_TASK_ID: task_id, OBS_HANDOFF: True},
        )
