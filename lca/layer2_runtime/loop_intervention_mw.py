"""Loop-intervention as ``agent.after_act`` middleware (spec §3.8.3)."""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.enums import ActionType
from lca.contracts.harness.middleware import MiddlewareRegistration
from lca.layer2_runtime.hook_middleware import middleware_bag

_LOOP_WARNING_WM_KEY = "loop_warning"
_LOOP_CONSECUTIVE_THRESHOLD = 3


async def loop_intervention_middleware(phase: str, state: Any, context: Any) -> Any:
    bag = middleware_bag(state)
    decision = bag.get("decision")
    observation = bag.get("observation")
    if decision is None or decision.action_type != ActionType.USE_TOOL:
        return state
    tool_calls = decision.tool_calls or []
    if not tool_calls:
        return state
    current_tool = tool_calls[0].tool_name
    consecutive = 0
    for turn in reversed(state.history):
        if (
            turn.decision.action_type == ActionType.USE_TOOL
            and turn.decision.tool_calls
            and turn.decision.tool_calls[0].tool_name == current_tool
        ):
            consecutive += 1
        else:
            break
    if consecutive >= _LOOP_CONSECUTIVE_THRESHOLD:
        tool_failed = observation is not None and not observation.success
        state.working_memory[_LOOP_WARNING_WM_KEY] = (
            f"⚠️ 你已连续 {consecutive} 次调用工具 {current_tool}"
            f"{'，且最近调用失败' if tool_failed else ''}。"
            f"请换一种方法或工具，不要继续重复相同的调用。"
        )
    return state


def install_loop_intervention(registry: Any) -> None:
    registry.register(
        MiddlewareRegistration(
            seam_key="agent.after_act",
            priority=20,
            plugin_id="lca.policy.loop_intervention",
        ),
        loop_intervention_middleware,
    )
