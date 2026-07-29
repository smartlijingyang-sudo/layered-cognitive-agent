"""FallbackActionPolicy."""

from __future__ import annotations

from lca.contracts.action import ActionRegistryProtocol
from lca.contracts.decision import Observation, StructuredDecision
from lca.contracts.enums import ActionType
from lca.contracts.ids import new_id
from lca.contracts.protocols import FallbackPolicy
from lca.contracts.semantic_keys import FALLBACK_DEGRADED_FROM
from lca.contracts.state import TypedState

FALLBACK_DEGRADATION_KEY = FALLBACK_DEGRADED_FROM


class FallbackActionPolicy(FallbackPolicy):
    async def handle(
        self,
        decision: StructuredDecision,
        state: TypedState,
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
            op = action_registry.resolve(ActionType.RESPOND)
            if op is not None:
                obs = await op.execute(decision, state)
                obs.degraded_from = original
                obs.extra[FALLBACK_DEGRADED_FROM] = original
                return obs
        if decision.tool_calls:
            op = action_registry.resolve(ActionType.USE_TOOL)
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
