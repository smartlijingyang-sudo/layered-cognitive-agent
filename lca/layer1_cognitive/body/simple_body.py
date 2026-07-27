"""SimpleBody —— L1 Body 实现，对外只暴露 act()。"""

from __future__ import annotations

import uuid
from typing import Any

from lca.contracts.state import TypedState
from lca.contracts.decision import StructuredDecision, Observation
from lca.contracts.result import ToolExecutionError
from lca.contracts.protocols import ToolRegistryP, SafeExecutorProtocol, Body
from lca.contracts.role_team import RetryPolicy, CacheConfig


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
            assert decision.tool_calls, "use_tool 需要至少一个 tool_call"
            tc = decision.tool_calls[0]
            tool = self.tool_registry.get(tc.tool_name)
            if tool is None:
                raise ToolExecutionError(f"未注册工具: {tc.tool_name}")
            return await self.safe_executor.execute(
                tool, tc.arguments, RetryPolicy(), CacheConfig()
            )

        raise ToolExecutionError(f"本示例暂未处理的 action_type: {decision.action_type}")
