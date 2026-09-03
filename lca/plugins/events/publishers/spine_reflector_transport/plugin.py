"""spine_reflector_transport plugin（ADR-0181 PR-4 / ADR-0183 PR-7）。

PR-4：transport / kernel.run 全部 6 emit 下沉到 EventBus.publish：
- transport.route.enter / .exit
- transport.sse.publish
- kernel.run.start / .stop / .cancelled

signature 严格对齐旧 lca/infrastructure/observability/spine/transport_emit.py
调用方零改动。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    """内部 helper：构造 SpineEventPayload + EventBus.publish。

    EventBus 走函数内 lazy import，避免 plugin import 时触发
    lca.infrastructure.observability ↔ lca_kernel 链路 circular import。
    """
    from lca_kernel.events.bus import EventBus

    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


# ── transport.route.enter / .exit ────────────────────────────────────


def emit_transport_route_enter(
    *,
    path: str,
    method: str,
    run_id: str | None = None,
    carrier_seq: int | None = None,
) -> EventRef:
    """Carrier-plane route enter。

    ADR-0166 S4：transport EP 携带 ``carrier_seq``（独立 carrier 单调计数）
    与 run-local ``EventRecord.sequence`` 解耦；reader 不会混淆两条 timeline。
    """
    payload: dict[str, Any] = {"path": path, "method": method, "run_id": run_id or ""}
    if carrier_seq is not None:
        payload["carrier_seq"] = carrier_seq
    return _send(
        execution_point="transport.route.enter",
        channel="control",
        payload=payload,
    )


def emit_transport_route_exit(
    *,
    path: str,
    method: str,
    outcome: str = "success",
    run_id: str | None = None,
    carrier_seq: int | None = None,
) -> EventRef:
    """Carrier-plane route exit（ADR-0166 S4）。"""
    payload: dict[str, Any] = {
        "path": path,
        "method": method,
        "run_id": run_id or "",
        "outcome": outcome,
    }
    if carrier_seq is not None:
        payload["carrier_seq"] = carrier_seq
    return _send(
        execution_point="transport.route.exit",
        channel="control",
        payload=payload,
    )


# ── transport.sse.publish ─────────────────────────────────────────────


def emit_transport_sse_publish(
    *,
    path: str,
    run_id: str | None = None,
) -> EventRef:
    return _send(
        execution_point="transport.sse.publish",
        channel="control",
        payload={"path": path, "run_id": run_id or ""},
    )


# ── kernel.run.start / .stop / .cancelled ─────────────────────────────


def emit_kernel_run_start(*, run_id: str, trace_id: str = "") -> EventRef:
    return _send(
        execution_point="kernel.run.start",
        channel="control",
        payload={"run_id": run_id, "trace_id": trace_id},
    )


def emit_kernel_run_stop(
    *,
    run_id: str,
    outcome: str = "success",
    trace_id: str = "",
) -> EventRef:
    return _send(
        execution_point="kernel.run.stop",
        channel="control",
        payload={"run_id": run_id, "trace_id": trace_id, "outcome": outcome},
    )


def emit_kernel_run_cancelled(*, run_id: str, trace_id: str = "") -> EventRef:
    return _send(
        execution_point="kernel.run.cancelled",
        channel="control",
        payload={"run_id": run_id, "trace_id": trace_id, "outcome": "cancelled"},
    )


__all__ = [
    "ReflectorClass",
    "emit_kernel_run_cancelled",
    "emit_kernel_run_start",
    "emit_kernel_run_stop",
    "emit_transport_route_enter",
    "emit_transport_route_exit",
    "emit_transport_sse_publish",
]
