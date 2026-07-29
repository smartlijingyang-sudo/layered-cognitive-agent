"""认知循环生命周期 Hook 定义与事件发射工厂。

L2 层职责：
    定义所有合法的 Hook 事件名（HOOK_NAMES），
    并提供 make_event_emitting_hook 工厂函数，
    将认知循环的关键事件（action_degraded、step_completed）
    发射到 EventBus，实现横切可观测性。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.enums import HookEvent
from lca.contracts.protocols import EventBus
from lca.contracts.state import TypedState

HOOK_NAMES = [
    "on_start",
    "pre_perceive",
    "post_perceive",
    "pre_think",
    "post_think",
    "pre_act",
    "post_act",
    "pre_reflect",
    "post_reflect",
    "on_error",
    "on_pause",
    "on_complete",
]


def make_event_emitting_hook(event_bus: EventBus) -> Callable[..., Awaitable[None]]:
    async def _hook(event_name: str, state: TypedState, **kwargs: Any) -> None:
        if event_name == HookEvent.POST_ACT:
            observation = kwargs.get("observation")
            if (
                observation is not None
                and getattr(observation, "success", False)
                and getattr(observation, "degraded_from", None)
            ):
                event_bus.emit(
                    "action_degraded",
                    {
                        "original_action_type": observation.degraded_from,
                        "degraded_to": "respond",
                        "step": state.step,
                    },
                    state.trace_id,
                )
        elif event_name == HookEvent.POST_REFLECT:
            event_bus.emit(
                "step_completed", {"step": state.step, "status": state.status}, state.trace_id
            )

    return _hook
