"""认知循环生命周期 Hook 定义与事件发射工厂。

L2 层职责：
    定义所有合法的 Hook 事件名（HOOK_NAMES），
    并提供 make_event_emitting_hook 工厂函数，
    将认知循环的关键事件（action_degraded、step_completed）
    发射到 EventBus，实现横切可观测性。

    新增对外事件只需：
    1. 写一个 _derive_xxx 函数
    2. 在 _DERIVATIONS 表中注册一行
    无需修改分支逻辑（开闭原则）。
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

# ── 事件派生：hook 事件名 → (对外事件名, payload) 提取函数 ──

EventDerivation = Callable[[TypedState, dict[str, Any]], tuple[str, dict[str, Any]] | None]


def _derive_action_degraded(
    state: TypedState, kwargs: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    observation = kwargs.get("observation")
    if (
        observation is not None
        and getattr(observation, "success", False)
        and getattr(observation, "degraded_from", None)
    ):
        return (
            "action_degraded",
            {
                "original_action_type": observation.degraded_from,
                "degraded_to": "respond",
                "step": state.step,
            },
        )
    return None


def _derive_step_completed(
    state: TypedState, kwargs: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    return ("step_completed", {"step": state.step, "status": state.status})


_DERIVATIONS: dict[str, EventDerivation] = {
    HookEvent.POST_ACT: _derive_action_degraded,
    HookEvent.POST_REFLECT: _derive_step_completed,
}


def make_event_emitting_hook(event_bus: EventBus) -> Callable[..., Awaitable[None]]:
    async def _hook(event_name: str, state: TypedState, **kwargs: Any) -> None:
        derive = _DERIVATIONS.get(event_name)
        if derive is None:
            return
        result = derive(state, kwargs)
        if result is not None:
            name, payload = result
            event_bus.emit(name, payload, state.trace_id)

    return _hook
