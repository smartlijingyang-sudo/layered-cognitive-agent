"""内置 Action 实现 —— 从 SimpleBody 提取的独立策略类。

每种 action_type 对应一个独立 Operation，彼此零依赖、零共享可变状态。
新增行动能力 = ActionCatalog 加一条 spec + 本模块一个 Operation + 注册。
"""

from __future__ import annotations

import asyncio

from lca.contracts.action import Action
from lca.contracts.decision import Decision, Observation
from lca.contracts.delegation_context import delegator_scope
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import (
    AgentTransport,
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy
from lca.contracts.semantic_keys import OBS_HANDOFF, OBS_TASK_ID
from lca.contracts.state import AgentState
from lca.layer1_cognitive.member_status.tracking import update_member_status

_POLL_INTERVAL_S = 0.05
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
    """处理 delegate 动作：阻塞式委派，等待目标 Agent 返回结果。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: Decision, state: AgentState) -> Observation:
        transport, task_id = await self._send_to_transport(decision, state)

        timeout_s = (
            (spec.deadline.timestamp() - asyncio.get_running_loop().time())
            if (spec := decision.delegate_to) and spec.deadline
            else _DEFAULT_DELEGATE_TIMEOUT_S
        )

        observation = await self._wait_for_result(transport, task_id, timeout_s)
        update_member_status(state, decision, observation)
        observation.extra[OBS_TASK_ID] = task_id
        return observation

    async def _wait_for_result(
        self,
        transport: AgentTransport,
        task_id: str,
        timeout_s: float,
    ) -> Observation:
        wait = getattr(transport, "wait_result", None)
        if wait is not None:
            try:
                result: Observation = await wait(task_id, timeout_s)
                return result
            except TimeoutError:
                return Observation(
                    observation_id=new_id("obs"),
                    success=False,
                    payload=None,
                    error=f"delegate 超时: task_id={task_id}",
                    extra={OBS_TASK_ID: task_id},
                )

        # 回退：跨进程 / 旧 transport 轮询
        elapsed = 0.0
        while (await transport.poll_status(task_id)) != TaskStatus.WORKING:
            if elapsed >= timeout_s:
                return Observation(
                    observation_id=new_id("obs"),
                    success=False,
                    payload=None,
                    error=f"delegate 超时: task_id={task_id}",
                    extra={OBS_TASK_ID: task_id},
                )
            await asyncio.sleep(_POLL_INTERVAL_S)
            elapsed += _POLL_INTERVAL_S
        return await transport.receive_result(task_id)

    async def _send_to_transport(
        self, decision: Decision, state: AgentState
    ) -> tuple[AgentTransport, str]:
        spec = decision.delegate_to
        if spec is None:
            raise ToolExecutionError(f"{decision.action_type} 动作缺少 delegate_to 规格")
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
        spec = decision.delegate_to
        if spec is None:
            raise ToolExecutionError("handoff 动作缺少 delegate_to 规格")
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
