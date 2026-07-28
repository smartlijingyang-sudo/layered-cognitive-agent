"""SimpleBody —— L1 Body 实现，对外只暴露 act()。"""

from __future__ import annotations

import asyncio
import uuid

from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols import AgentTransport, Body, SafeExecutor, ToolRegistry
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy
from lca.contracts.state import TypedState, _current_delegator
from lca.layer0_infra.transport.transport_registry import TransportRegistry

_POLL_INTERVAL_S = 0.05

_ACTION_HANDLERS: dict[str, str] = {
    "respond": "_handle_respond",
    "use_tool": "_handle_use_tool",
    "delegate": "_handle_delegate",
    "handoff": "_handle_handoff",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleBody(Body):
    """ToolRegistry + SafeExecutor 组合，通过 TransportRegistry 按协议路由 delegate。"""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistry | None = None,
        transport: AgentTransport | None = None,
    ):
        self.tool_registry = tool_registry
        self.safe_executor = safe_executor
        if transport_registry is not None:
            self.transport_registry = transport_registry
        elif transport is not None:
            registry = TransportRegistry()
            registry.register(transport)
            self.transport_registry = registry
        else:
            self.transport_registry = TransportRegistry()

    def bind_transport(self, transport: AgentTransport) -> None:
        self.transport_registry.register(transport)

    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation:
        handler_name = _ACTION_HANDLERS.get(decision.action_type)
        if handler_name is None:
            raise ToolExecutionError(f"本示例暂未处理的 action_type: {decision.action_type}")
        handler = getattr(self, handler_name)
        result: Observation = await handler(decision, state)
        return result

    async def _handle_respond(self, decision: StructuredDecision, state: TypedState) -> Observation:
        return Observation(
            observation_id=_new_id("obs"),
            success=True,
            payload=decision.response_text,
        )

    async def _handle_use_tool(
        self, decision: StructuredDecision, state: TypedState
    ) -> Observation:
        if not decision.tool_calls:
            raise ToolExecutionError("use_tool 需要至少一个 tool_call")
        tc = decision.tool_calls[0]
        tool = self.tool_registry.get(tc.tool_name)
        if tool is None:
            raise ToolExecutionError(f"未注册工具: {tc.tool_name}")
        return await self.safe_executor.execute(tool, tc.arguments, RetryPolicy(), CacheConfig())

    async def _handle_delegate(
        self, decision: StructuredDecision, state: TypedState
    ) -> Observation:
        transport, task_id = await self._send_to_transport(decision, state)

        timeout_s = (
            (spec.deadline.timestamp() - asyncio.get_event_loop().time())
            if (spec := decision.delegate_to) and spec.deadline
            else 30.0
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

    async def _handle_handoff(self, decision: StructuredDecision, state: TypedState) -> Observation:
        """轻量控制权移交：把任务发给目标 Agent 后立即返回，不轮询等待。

        与 delegate 的区别：
        - delegate：阻塞式，等待目标 Agent 返回结果
        - handoff：非阻塞，发完即退出当前 Agent 的 loop，由目标 Agent 接管
        """
        _transport, task_id = await self._send_to_transport(decision, state)
        spec = decision.delegate_to
        return Observation(
            observation_id=_new_id("obs"),
            success=True,
            payload=f"handoff to {spec.target_role or spec.target_agent_id if spec else 'unknown'}",
            extra={"task_id": task_id, "handoff": True},
        )

    async def _send_to_transport(
        self, decision: StructuredDecision, state: TypedState
    ) -> tuple[AgentTransport, str]:
        """resolve transport + 拼装 agent_card + send_task 的共用逻辑。"""
        spec = decision.delegate_to
        if spec is None:
            raise ToolExecutionError(f"{decision.action_type} 动作缺少 delegate_to 规格")

        transport = self.transport_registry.resolve(spec.protocol)
        agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
        # 设置当前委派者，让目标 Agent 的 handler 能读取
        _current_delegator.set(state.agent_role)
        task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)
        return transport, task_id
