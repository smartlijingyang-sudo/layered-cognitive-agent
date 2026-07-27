"""SimpleBody —— L1 Body 实现，对外只暴露 act()。"""

from __future__ import annotations

import asyncio
import uuid

from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols import AgentTransport, Body, SafeExecutorProtocol, ToolRegistryP
from lca.contracts.result import ToolExecutionError
from lca.contracts.role_team import CacheConfig, RetryPolicy
from lca.contracts.state import TypedState
from lca.layer0_infra.transport.transport_registry import TransportRegistry

_POLL_INTERVAL_S = 0.05


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleBody(Body):
    """ToolRegistry + SafeExecutor 组合，通过 TransportRegistry 按协议路由 delegate。"""

    def __init__(
        self,
        tool_registry: ToolRegistryP,
        safe_executor: SafeExecutorProtocol,
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
        if decision.action_type == "respond":
            return Observation(
                observation_id=_new_id("obs"),
                success=True,
                payload=decision.response_text,
            )

        if decision.action_type == "use_tool":
            if not decision.tool_calls:
                raise ToolExecutionError("use_tool 需要至少一个 tool_call")
            tc = decision.tool_calls[0]
            tool = self.tool_registry.get(tc.tool_name)
            if tool is None:
                raise ToolExecutionError(f"未注册工具: {tc.tool_name}")
            return await self.safe_executor.execute(
                tool, tc.arguments, RetryPolicy(), CacheConfig()
            )

        if decision.action_type == "delegate":
            return await self._handle_delegate(decision)

        raise ToolExecutionError(f"本示例暂未处理的 action_type: {decision.action_type}")

    async def _handle_delegate(self, decision: StructuredDecision) -> Observation:
        spec = decision.delegate_to
        if spec is None:
            raise ToolExecutionError("delegate 动作缺少 delegate_to 规格")

        transport = self.transport_registry.resolve(spec.protocol)

        agent_card = spec.target_agent_card or spec.target_agent_id or spec.target_role
        task_id = await transport.send_task(agent_card, spec.subtask, spec.context_refs)

        timeout_s = (
            (spec.deadline.timestamp() - asyncio.get_event_loop().time()) if spec.deadline else 30.0
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
