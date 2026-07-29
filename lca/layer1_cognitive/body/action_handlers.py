"""内置 ActionOperation 实现 —— 从 SimpleBody 提取的独立策略类。

每种 action_type 对应一个独立 Operation，彼此零依赖、零共享可变状态。
新增行动能力 = 新增一个 Operation + 一条注册。
"""

from __future__ import annotations

import asyncio
import uuid

from lca.contracts.action import ActionOperation
from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols import (
    AgentTransport,
    SafeExecutor,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy
from lca.contracts.state import TypedState
from lca.layer1_cognitive.body.action_registry import ActionRegistry

_POLL_INTERVAL_S = 0.05
_DEFAULT_DELEGATE_TIMEOUT_S = 30.0


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RespondOperation(ActionOperation):
    """处理 respond 动作：直接返回文本响应。"""

    async def execute(self, decision: StructuredDecision, state: TypedState) -> Observation:
        return Observation(
            observation_id=_new_id("obs"),
            success=True,
            payload=decision.response_text,
        )


class UseToolOperation(ActionOperation):
    """处理 use_tool 动作：查找工具 → 权限校验 → 执行。"""

    def __init__(self, tool_registry: ToolRegistry, safe_executor: SafeExecutor) -> None:
        self._tool_registry = tool_registry
        self._safe_executor = safe_executor

    async def execute(self, decision: StructuredDecision, state: TypedState) -> Observation:
        if not decision.tool_calls:
            raise ToolExecutionError("use_tool 需要至少一个 tool_call")
        tc = decision.tool_calls[0]
        tool = self._tool_registry.get(tc.tool_name)
        if tool is None:
            raise ToolExecutionError(f"未注册工具: {tc.tool_name}")
        return await self._safe_executor.execute(tool, tc.arguments, RetryPolicy(), CacheConfig())


class DelegateOperation(ActionOperation):
    """处理 delegate 动作：阻塞式委派，等待目标 Agent 返回结果。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: StructuredDecision, state: TypedState) -> Observation:
        transport, task_id = await self._send_to_transport(decision, state)

        timeout_s = (
            (spec.deadline.timestamp() - asyncio.get_event_loop().time())
            if (spec := decision.delegate_to) and spec.deadline
            else _DEFAULT_DELEGATE_TIMEOUT_S
        )
        elapsed = 0.0
        while (await transport.poll_status(task_id)) == "working":
            if elapsed >= timeout_s:
                return Observation(
                    observation_id=_new_id("obs"),
                    success=False,
                    payload=None,
                    error=f"delegate 超时: task_id={task_id}",
                    extra={"task_id": task_id},
                )
            await asyncio.sleep(_POLL_INTERVAL_S)
            elapsed += _POLL_INTERVAL_S

        observation = await transport.receive_result(task_id)
        observation.extra["task_id"] = task_id
        return observation

    async def _send_to_transport(
        self, decision: StructuredDecision, state: TypedState
    ) -> tuple[AgentTransport, str]:
        spec = decision.delegate_to
        if spec is None:
            raise ToolExecutionError(f"{decision.action_type} 动作缺少 delegate_to 规格")
        transport = self._transport_registry.resolve(spec.protocol)
        agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
        with delegator_scope(state.agent_role):
            task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        return transport, task_id


class HandoffOperation(ActionOperation):
    """处理 handoff 动作：非阻塞控制权移交，发完即返回。"""

    def __init__(self, transport_registry: TransportRegistryProtocol) -> None:
        self._transport_registry = transport_registry

    async def execute(self, decision: StructuredDecision, state: TypedState) -> Observation:
        spec = decision.delegate_to
        if spec is None:
            raise ToolExecutionError("handoff 动作缺少 delegate_to 规格")
        transport = self._transport_registry.resolve(spec.protocol)
        agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
        with delegator_scope(state.agent_role):
            task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        return Observation(
            observation_id=_new_id("obs"),
            success=True,
            payload=f"handoff to {spec.target_role or spec.target_agent_id}",
            extra={"task_id": task_id, "handoff": True},
        )


# 过渡期 alias
RespondHandler = RespondOperation
UseToolHandler = UseToolOperation
DelegateHandler = DelegateOperation
HandoffHandler = HandoffOperation


def build_default_action_registry(
    tool_registry: ToolRegistry,
    safe_executor: SafeExecutor,
    transport_registry: TransportRegistryProtocol,
) -> ActionRegistry:
    """构建包含所有内置 ActionOperation 的默认注册表。"""
    registry = ActionRegistry()
    registry.register("respond", RespondOperation())
    registry.register("use_tool", UseToolOperation(tool_registry, safe_executor))
    registry.register("delegate", DelegateOperation(transport_registry))
    registry.register("handoff", HandoffOperation(transport_registry))
    return registry
