"""EventBus → 遥测事件桥（Observer 模式）——双通道合一。

认知循环经 ``make_event_emitting_hook`` 把业务事实发到 EventBus；
本桥把总线事件转成遥测事件（ambient ``event()``），从此 bus 事件
进入同一条 trace 管道（console/jsonl/langfuse 全可见）。

桥在 L4 装配（订阅是组合动作）；发射走 ambient 上下文——EventBus
的 asyncio task 拷贝发射时刻的 contextvars，hub 与 span 上下文自动继承。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import EventBus
from lca.contracts.telemetry import ATTR_STATUS, ATTR_STEP, EventName
from lca.layer0_infra.observability import event
from lca.layer2_runtime.event_emission import EVENT_ACTION_DEGRADED, EVENT_STEP_COMPLETED

_KEY_ORIGINAL = "original_action_type"
_KEY_DEGRADED_TO = "degraded_to"
_KEY_STEP = "step"


def _inner(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("payload")
    return data if isinstance(data, dict) else {}


async def _on_action_degraded(payload: dict[str, Any]) -> None:
    data = _inner(payload)
    event(
        EventName.ACTION_DEGRADED,
        **{
            _KEY_ORIGINAL: data.get(_KEY_ORIGINAL, ""),
            _KEY_DEGRADED_TO: data.get(_KEY_DEGRADED_TO, ""),
            ATTR_STEP: data.get(_KEY_STEP, 0),
        },
    )


async def _on_step_completed(payload: dict[str, Any]) -> None:
    data = _inner(payload)
    status = data.get(ATTR_STATUS, "")
    event(
        EventName.STEP_COMPLETED,
        **{ATTR_STEP: data.get(_KEY_STEP, 0), ATTR_STATUS: getattr(status, "value", str(status))},
    )


def install_telemetry_bridge(event_bus: EventBus) -> None:
    """订阅业务事件并转发到遥测通道（组合根调用一次）。"""
    event_bus.subscribe(EVENT_ACTION_DEGRADED, _on_action_degraded)
    event_bus.subscribe(EVENT_STEP_COMPLETED, _on_step_completed)
