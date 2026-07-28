"""生命周期钩子清单与默认事件发布钩子。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.protocols import EventBus
from lca.contracts.state import TypedState
from lca.layer2_runtime.fallback_handler import FALLBACK_DEGRADATION_KEY

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


def make_event_emitting_hook(
    event_bus: EventBus,
) -> Callable[..., Awaitable[None]]:
    """工厂：创建将 Loop 事件桥接到 EventBus 的钩子函数。

    注册到 post_act（检测降级事件）和 post_reflect（发布 step_completed），
    使 Loop 本体不再直接调用 event_bus.emit()。
    """

    async def _event_emitting_hook(event_name: str, state: TypedState, **kwargs: Any) -> None:
        if event_name == "post_act":
            observation = kwargs.get("observation")
            if (
                observation is not None
                and getattr(observation, "success", False)
                and FALLBACK_DEGRADATION_KEY in getattr(observation, "extra", {})
            ):
                event_bus.emit(
                    "action_degraded",
                    {
                        "original_action_type": observation.extra[FALLBACK_DEGRADATION_KEY],
                        "degraded_to": "respond",
                        "step": state.step,
                    },
                    state.trace_id,
                )
        elif event_name == "post_reflect":
            event_bus.emit(
                "step_completed",
                {"step": state.step, "status": state.status},
                state.trace_id,
            )

    return _event_emitting_hook
