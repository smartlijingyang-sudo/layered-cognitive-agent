"""Carrier-plane spine emit helpers — ADR-0165.1 transport / kernel.run.

Lives under ``infrastructure`` so ``lca.plugins.transport`` can emit without
importing ``lca.plugins.observability`` (plugin-package independence).

Uses the process-local spine accessor installed by ``spine.core``
(``set_active_spine_accessor``). Helpers no-op when unwired.

异常事件走 :mod:`lca.infrastructure.observability.spine.exception_emit`
唯一 emitter(SSOT):先 :func:`lca.contracts.observability.exc_to_record`
归一化,再 ``emit_exception_caught(record)``。
"""

from __future__ import annotations

import logging
from typing import Any

from lca.harness.declarative.compile.instrument_wrap import resolve_active_spine
from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
)

log = logging.getLogger(__name__)


def _safe_append(
    *,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
) -> EventRecord | None:
    spine = resolve_active_spine()
    if spine is None:
        return None
    try:
        return spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=payload,
            outcome=outcome,
        )
    except ValueError as exc:
        log.warning(
            "transport_emit: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
        )
        return None


def emit_transport_route_enter(
    *,
    path: str,
    method: str,
    run_id: str | None = None,
    carrier_seq: int | None = None,
) -> EventRecord | None:
    """Carrier-plane route enter.

    ADR-0166 S4：transport EP 携带 ``carrier_seq``（独立 carrier 单调计数）
    与 run-local ``EventRecord.sequence`` 解耦；reader 不会混淆两条 timeline。
    """
    payload: dict[str, Any] = {"path": path, "method": method, "run_id": run_id or ""}
    if carrier_seq is not None:
        payload["carrier_seq"] = carrier_seq
    return _safe_append(
        execution_point="transport.route.enter",
        channel="control",
        payload=payload,
    )


def emit_transport_route_exit(
    *,
    path: str,
    method: str,
    outcome: Outcome = "success",
    run_id: str | None = None,
    carrier_seq: int | None = None,
) -> EventRecord | None:
    """Carrier-plane route exit（ADR-0166 S4）。"""
    payload: dict[str, Any] = {"path": path, "method": method, "run_id": run_id or ""}
    if carrier_seq is not None:
        payload["carrier_seq"] = carrier_seq
    return _safe_append(
        execution_point="transport.route.exit",
        channel="control",
        payload=payload,
        outcome=outcome,
    )


def emit_transport_sse_publish(
    *,
    path: str,
    run_id: str | None = None,
) -> EventRecord | None:
    return _safe_append(
        execution_point="transport.sse.publish",
        channel="control",
        payload={"path": path, "run_id": run_id or ""},
    )


def emit_kernel_run_start(*, run_id: str, trace_id: str = "") -> EventRecord | None:
    return _safe_append(
        execution_point="kernel.run.start",
        channel="control",
        payload={"run_id": run_id, "trace_id": trace_id},
    )


def emit_kernel_run_stop(
    *,
    run_id: str,
    outcome: Outcome = "success",
    trace_id: str = "",
) -> EventRecord | None:
    return _safe_append(
        execution_point="kernel.run.stop",
        channel="control",
        payload={"run_id": run_id, "trace_id": trace_id},
        outcome=outcome,
    )


def emit_kernel_run_cancelled(*, run_id: str, trace_id: str = "") -> EventRecord | None:
    return _safe_append(
        execution_point="kernel.run.cancelled",
        channel="control",
        payload={"run_id": run_id, "trace_id": trace_id},
        outcome="cancelled",
    )


def emit_carrier_exception_finally(
    *,
    boundary: str,
    run_id: str = "",
    trace_id: str = "",
) -> EventRecord | None:
    return _safe_append(
        execution_point="exception.finally",
        channel="diagnostic",
        payload={
            "boundary": boundary,
            "run_id": run_id,
            "trace_id": trace_id,
        },
    )


__all__ = [
    "emit_carrier_exception_finally",
    "emit_kernel_run_cancelled",
    "emit_kernel_run_start",
    "emit_kernel_run_stop",
    "emit_transport_route_enter",
    "emit_transport_route_exit",
    "emit_transport_sse_publish",
]
