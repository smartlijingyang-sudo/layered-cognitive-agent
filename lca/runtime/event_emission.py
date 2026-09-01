"""认知循环 → journal 直接发射（开闭原则，ADR-0037）+ Waterfall 拦截。

认知循环的横切事实（action_degraded / step_completed）由 hook 捕获后
直接构造 ``JournalEvent`` 实例，通过 ``JournalEmitFn`` 回调写入 journal。

**不再经过 EventBus 中转**：EventBus 是泛型 dict 载荷，丢失类型安全；
telemetry_bridge 桥接层是纯粹的间接浪费——emit/subscribe/record 三点一线，
中间总线毫无存在必要。

Waterfall 拦截：
    在事件发射前，可以通过 waterfall 链进行拦截/修改/过滤。
    每个 waterfall listener 可以：
    - 修改事件字段（enrichment）
    - 返回 None 过滤掉事件（filtering）
    - 透传给下一个 listener

新增对外事件只需：
    1. 写一个 _derive_xxx 纯函数
    2. 在 _DERIVATIONS 表中注册一行
无需修改分支逻辑（开闭原则）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.atoms.enums import ActionType, HookEvent
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.observability.journal import (
    ActionDegraded,
    JournalEvent,
    StepCompleted,
)

# ── journal 发射回调类型 ──
JournalEmitFn = Callable[[JournalEvent], None]
"""接收已构造的 JournalEvent 并写入 journal 的回调。
组合根注入 ``lca.infrastructure.observability.facade.record``。"""

# ── Waterfall 拦截器类型 ──
JournalEventWaterfallFn = Callable[[JournalEvent, AgentState], JournalEvent | None]
"""Waterfall 拦截器：接收事件和状态，返回修改后的事件或 None（过滤）。
用于事件发射前的拦截/修改/过滤链。"""

# ── 事件派生：hook 事件名 → JournalEvent 构造 ──

Derivation = Callable[[AgentState, dict[str, Any]], JournalEvent | None]


def _derive_action_degraded(state: AgentState, kwargs: dict[str, Any]) -> JournalEvent | None:
    observation = kwargs.get("observation")
    if (
        observation is not None
        and getattr(observation, "success", False)
        and getattr(observation, "degraded_from", None)
    ):
        decision = kwargs.get("decision")
        degraded_to = getattr(decision, "action_type", None) or ActionType.RESPOND.value
        return ActionDegraded(
            original_action_type=observation.degraded_from,
            degraded_to=degraded_to,
            step=state.step,
        )
    return None


def _derive_step_completed(state: AgentState, kwargs: dict[str, Any]) -> JournalEvent | None:
    status = state.status
    # ADR-0164 Phase 3 双写:StepCompleted 收口也关闭当前 step
    try:
        from lca.runtime.step_emitter import bridge_step_completed_emitted

        bridge_step_completed_emitted(
            status=getattr(status, "value", str(status)),
        )
    except ImportError:
        pass
    return StepCompleted(
        step=state.step,
        status=getattr(status, "value", str(status)),
        action_type=kwargs.get("action_type", ""),
    )


_DERIVATIONS: dict[str, Derivation] = {
    HookEvent.POST_ACT: _derive_action_degraded,
    HookEvent.POST_REFLECT: _derive_step_completed,
}


def make_journal_emitting_hook(
    emit: JournalEmitFn,
    *,
    waterfall: list[JournalEventWaterfallFn] | None = None,
) -> Callable[..., Awaitable[None]]:
    """构造认知循环 → journal 直写 hook，支持 waterfall 拦截。

    ``emit`` 由组合根注入（通常是 ``facade.record``），L2 不依赖 L0。

    ``waterfall`` 是可选的拦截器链：
    - 每个拦截器可以修改事件或返回 None 过滤掉事件
    - 拦截器按顺序执行，前一个的输出是后一个的输入
    - 任何拦截器返回 None 则事件不会被发射

    用法示例：
        # 添加事件过滤
        def filter_sensitive(event: JournalEvent, state: AgentState) -> JournalEvent | None:
            if isinstance(event, ActionDegraded) and "secret" in event.original_action_type:
                return None  # 过滤掉敏感事件
            return event

        hook = make_journal_emitting_hook(emit, waterfall=[filter_sensitive])
    """

    async def _hook(event_name: str, state: AgentState, **kwargs: Any) -> None:
        derive = _DERIVATIONS.get(event_name)
        if derive is None:
            return
        event = derive(state, kwargs)
        if event is None:
            return

        # Waterfall 拦截链
        if waterfall:
            for interceptor in waterfall:
                event = interceptor(event, state)
                if event is None:
                    return  # 事件被过滤

        emit(event)

    return _hook
