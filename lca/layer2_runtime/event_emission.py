"""认知循环生命周期 Hook 事件发射工厂。

L2 层职责：
    提供 make_event_emitting_hook 工厂函数，
    将认知循环的关键事件（action_degraded、step_completed）
    发射到 EventBus，实现横切可观测性。

    Hook 事件名的单一事实源是 ``HookEvent`` 枚举（``lca.contracts.atoms.enums``）。
    新增对外事件只需：
    1. 写一个 _derive_xxx 函数
    2. 在 _DERIVATIONS 表中注册一行
    无需修改分支逻辑（开闭原则）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.atoms.enums import ActionType, HookEvent
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import EventBus

# ── 对外事件名（EventBus payload） ──
EVENT_ACTION_DEGRADED = "action_degraded"
EVENT_STEP_COMPLETED = "step_completed"

# ── payload 键 ──
_KEY_ORIGINAL_ACTION_TYPE = "original_action_type"
_KEY_DEGRADED_TO = "degraded_to"
_KEY_STEP = "step"
_KEY_STATUS = "status"

# ── 事件派生：hook 事件名 → (对外事件名, payload) 提取函数 ──

EventDerivation = Callable[[AgentState, dict[str, Any]], tuple[str, dict[str, Any]] | None]


def _derive_action_degraded(
    state: AgentState, kwargs: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    observation = kwargs.get("observation")
    if (
        observation is not None
        and getattr(observation, "success", False)
        and getattr(observation, "degraded_from", None)
    ):
        # 降级目标取改写后的 decision.action_type（respond / use_tool 均可能）；
        # decision 缺省时退回历史默认 respond。
        decision = kwargs.get("decision")
        degraded_to = getattr(decision, "action_type", None) or ActionType.RESPOND.value
        return (
            EVENT_ACTION_DEGRADED,
            {
                _KEY_ORIGINAL_ACTION_TYPE: observation.degraded_from,
                _KEY_DEGRADED_TO: degraded_to,
                _KEY_STEP: state.step,
            },
        )
    return None


def _derive_step_completed(
    state: AgentState, kwargs: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    return (
        EVENT_STEP_COMPLETED,
        {_KEY_STEP: state.step, _KEY_STATUS: state.status},
    )


_DERIVATIONS: dict[str, EventDerivation] = {
    HookEvent.POST_ACT: _derive_action_degraded,
    HookEvent.POST_REFLECT: _derive_step_completed,
}


def make_event_emitting_hook(event_bus: EventBus) -> Callable[..., Awaitable[None]]:
    async def _hook(event_name: str, state: AgentState, **kwargs: Any) -> None:
        derive = _DERIVATIONS.get(event_name)
        if derive is None:
            return
        result = derive(state, kwargs)
        if result is not None:
            name, payload = result
            event_bus.emit(name, payload, state.trace_id)

    return _hook
