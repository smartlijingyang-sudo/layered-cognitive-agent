"""SimpleBody —— L1 Body 实现，对外只暴露 act()。"""

from __future__ import annotations

import uuid
from typing import Any

from contracts.state import TypedState
from contracts.decision import StructuredDecision, Observation
from contracts.result import ToolExecutionError
from contracts.protocols import ToolRegistryP, SafeExecutorProtocol, Body
from contracts.role_team import RetryPolicy, CacheConfig


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SimpleBody(Body):
    """ToolRegistry + SafeExecutor 组合。"""

    def __init__(self, tool_registry: ToolRegistryP, safe_executor: SafeExecutorProtocol):
        self.tool_registry = tool_registry
        self.safe_executor = safe_executor

    async def act(self, decision: StructuredDecision, state: TypedState) -> Observation:
        if decision.action_type == "respond":
            return Observation(observation_id=_new_id("obs"), success=True, payload=decision.response_text)

        if decision.action_type == "use_tool":
            assert decision.tool_call is not None
            tool = self.tool_registry.get(decision.tool_call.tool_name)
            if tool is None:
                raise ToolExecutionError(f"未注册工具: {decision.tool_call.tool_name}")
            return await self.safe_executor.execute(
                tool, decision.tool_call.arguments, RetryPolicy(), CacheConfig()
            )

        raise ToolExecutionError(f"本示例暂未处理的 action_type: {decision.action_type}")
