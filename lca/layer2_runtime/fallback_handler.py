"""FallbackActionPolicy —— 未知 action 的链式降级（Chain of Responsibility）。

当 ActionRegistry 无法解析 action_type 时，
按优先级尝试降级策略，避免"契约违反"直接升级为"业务失败"。

降级优先级：
  1. 有 response_text → 语义等价于 respond
  2. 有 tool_calls   → 语义等价于 use_tool
  3. 都没有          → 不可恢复失败
"""

from __future__ import annotations

import uuid

from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.protocols import FallbackPolicy
from lca.contracts.state import TypedState
from lca.layer1_cognitive.body.action_registry import ActionRegistryProtocol

FALLBACK_DEGRADATION_KEY = "degraded_from_action_type"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


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
                observation_id=_new_id("obs"),
                success=False,
                payload=None,
                error=f"无法识别的 action_type '{original_action_type}' 且无可用的 ActionRegistry",
                extra={FALLBACK_DEGRADATION_KEY: original_action_type},
            )

        # 策略 1：有 response_text → 降级为 respond
        if decision.response_text:
            respond_op = action_registry.resolve("respond")
            if respond_op is not None:
                observation = await respond_op.execute(decision, state)
                observation.extra[FALLBACK_DEGRADATION_KEY] = original_action_type
                return observation

        # 策略 2：有 tool_calls → 降级为 use_tool
        if decision.tool_calls:
            use_tool_op = action_registry.resolve("use_tool")
            if use_tool_op is not None:
                observation = await use_tool_op.execute(decision, state)
                observation.extra[FALLBACK_DEGRADATION_KEY] = original_action_type
                return observation

        # 策略 3：不可恢复失败
        return Observation(
            observation_id=_new_id("obs"),
            success=False,
            payload=None,
            error=f"无法识别的 action_type '{original_action_type}' 且无可用降级路径",
            extra={FALLBACK_DEGRADATION_KEY: original_action_type},
        )


# 过渡期 alias
FallbackActionHandler = FallbackActionPolicy
