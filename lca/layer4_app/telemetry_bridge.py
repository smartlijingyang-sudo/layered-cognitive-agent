"""EventBus → journal 桥（Observer 模式）——双通道合一（ADR-0037）。

认知循环经 ``make_event_emitting_hook`` 把业务事实发到 EventBus；
本桥把总线事件转成 journal 事件（ambient ``record``），由此进入统一的
执行日志（OTel 投影为所属 run span 的 event，不再是孤儿 0 秒 span）。

桥在 L4 装配（订阅是组合动作）；发射走 ambient 上下文——EventBus
的 asyncio task 拷贝发射时刻的 contextvars，journal 关联骨架自动继承。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.models.observability.journal import ActionDegraded, StepCompleted
from lca.contracts.protocols import EventBus
from lca.layer0_infra.observability import record
from lca.layer2_runtime.event_emission import EVENT_ACTION_DEGRADED, EVENT_STEP_COMPLETED

_KEY_ORIGINAL = "original_action_type"
_KEY_DEGRADED_TO = "degraded_to"
_KEY_STEP = "step"


def _inner(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("payload")
    return data if isinstance(data, dict) else {}


async def _on_action_degraded(payload: dict[str, Any]) -> None:
    data = _inner(payload)
    record(
        ActionDegraded(
            original_action_type=data.get(_KEY_ORIGINAL, ""),
            degraded_to=data.get(_KEY_DEGRADED_TO, ""),
            step=data.get(_KEY_STEP, 0),
        )
    )


async def _on_step_completed(payload: dict[str, Any]) -> None:
    data = _inner(payload)
    status = data.get("status", "")
    record(
        StepCompleted(
            step=data.get(_KEY_STEP, 0),
            status=getattr(status, "value", str(status)),
            action_type=data.get("action_type", ""),
        )
    )


def install_telemetry_bridge(event_bus: EventBus) -> None:
    """订阅业务事件并转发到 journal（组合根调用一次）。"""
    event_bus.subscribe(EVENT_ACTION_DEGRADED, _on_action_degraded)
    event_bus.subscribe(EVENT_STEP_COMPLETED, _on_step_completed)


def make_bus_drain_hook(event_bus: EventBus) -> Callable[..., Awaitable[None]]:
    """on_complete 钩子：run 收尾前排空总线，桥接事件先于容器关闭落入 journal。"""

    async def _hook(_event_name: str, _state: object, **_kwargs: Any) -> None:
        await event_bus.drain()

    return _hook
