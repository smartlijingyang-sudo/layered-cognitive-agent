"""FallbackActionPolicy —— 未识别 action_type 的降级策略。

L1 层职责：
    当 Brain 输出的 action_type 无法被 ActionRegistry 识别时，
    按优先级尝试降级路径：RESPOND → USE_TOOL → 失败。
    降级后的 Observation 携带 degraded_from 标记，供 hook 观测。
"""

from __future__ import annotations

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Decision, Observation
from lca.contracts.enums import ActionType
from lca.contracts.ids import new_id
from lca.contracts.protocols import FallbackPolicy
from lca.contracts.semantic_keys import FALLBACK_DEGRADED_FROM
from lca.contracts.state import AgentState


class FallbackActionPolicy(FallbackPolicy):
    """未识别 action_type 的降级策略。

    降级优先级：
    1. 有 response_text → 降级为 RESPOND
    2. 有 tool_calls → 降级为 USE_TOOL
    3. 均无 → 返回失败 Observation
    """

    async def handle(
        self,
        decision: Decision,
        state: AgentState,
        action_registry: ActionRegistryProtocol | None = None,
    ) -> Observation:
        original = decision.action_type
        if action_registry is None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"无法识别的 action_type '{original}' 且无可用的 ActionRegistry",
                degraded_from=original,
                extra={FALLBACK_DEGRADED_FROM: original},
            )
        if decision.response_text:
            op = action_registry.get(ActionType.RESPOND)
            if op is not None:
                obs = await op.execute(decision, state)
                obs.degraded_from = original
                obs.extra[FALLBACK_DEGRADED_FROM] = original
                return obs
        if decision.tool_calls:
            op = action_registry.get(ActionType.USE_TOOL)
            if op is not None:
                obs = await op.execute(decision, state)
                obs.degraded_from = original
                obs.extra[FALLBACK_DEGRADED_FROM] = original
                return obs
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=f"无法识别的 action_type '{original}' 且无可用降级路径",
            degraded_from=original,
            extra={FALLBACK_DEGRADED_FROM: original},
        )
