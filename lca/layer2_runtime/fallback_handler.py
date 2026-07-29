"""FallbackActionPolicy —— 未知 action 的链式降级（Chain of Responsibility）。

当 ActionRegistry 无法解析 action_type 时，
按优先级尝试降级策略，避免"契约违反"直接升级为"业务失败"。

降级优先级：
  1. 有 response_text → 语义等价于 respond
  2. 有 tool_calls   → 语义等价于 use_tool
  3. 都没有          → 不可恢复失败
"""

from __future__ import annotations

from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.ids import new_id
from lca.contracts.protocols import FallbackPolicy
from lca.contracts.semantic_keys import FALLBACK_DEGRADED_FROM
from lca.contracts.state import TypedState
from lca.layer1_cognitive.body.action_registry import ActionRegistryProtocol

# 向后兼容导出
FALLBACK_DEGRADATION_KEY = FALLBACK_DEGRADED_FROM


class FallbackActionPolicy(FallbackPolicy):
    """未知 action_type 的兜底策略。

    本身不注册到 ActionRegistry 中（Registry 是无状态纯路由），
    而是由 Body 装饰器（FallbackDecoratedBody）在捕获到
    "未注册的 action_type" 错误时显式调用。
    """

    async def handle(
        self,
        decision: StructuredDecision,
        state: TypedState,
        action_registry: ActionRegistryProtocol | None = None,
    ) -> Observation:
        original_action_type = decision.action_type

        if action_registry is None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"无法识别的 action_type '{original_action_type}' 且无可用的 ActionRegistry",
                extra={FALLBACK_DEGRADED_FROM: original_action_type},
            )

        if decision.response_text:
            respond_op = action_registry.resolve("respond")
            if respond_op is not None:
                observation = await respond_op.execute(decision, state)
                observation.extra[FALLBACK_DEGRADED_FROM] = original_action_type
                return observation

        if decision.tool_calls:
            use_tool_op = action_registry.resolve("use_tool")
            if use_tool_op is not None:
                observation = await use_tool_op.execute(decision, state)
                observation.extra[FALLBACK_DEGRADED_FROM] = original_action_type
                return observation

        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=f"无法识别的 action_type '{original_action_type}' 且无可用降级路径",
            extra={FALLBACK_DEGRADED_FROM: original_action_type},
        )
