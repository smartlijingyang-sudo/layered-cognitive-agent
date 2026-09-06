"""异常事件唯一 emitter —— 任何路径任何时机的异常都走这里。

ADR-0169 + ADR-2026-09-02-i17-stream-align §B: SSOT 异常归一化
(:class:`lca.contracts.observability.exception_capture.ExceptionRecord`)
产生后,**只能** 通过 :func:`emit_exception_caught` 落 spine event。

生产路径优先经 ``FactGateway.publish_ep``(Session SSOT);无 bound Session 时
回退 process-local ``EventSpine``(测试 / instrument_wrap)。
"""

from __future__ import annotations

from typing import Any, Literal

from lca.contracts.observability import ExceptionRecord as ExceptionRecordT
from lca.contracts.observability.evidence.outcome import Outcome
from lca.harness.declarative.compile.instrument.wrap import resolve_active_spine
from lca.infrastructure.observability.spine.event.record import Channel, EventRecord

_EXECUTION_POINT = "exception.caught"
_CHANNEL_ERROR: Literal["error"] = "error"
_OUTCOME_FAILURE: Literal["failure"] = "failure"
_EMIT_ACTOR = "exception.emit"


def _safe_append(
    *,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any] | None = None,
    outcome: Outcome | None = None,
) -> EventRecord | None:
    """Append via process-local spine accessor (tests / unwired runs)."""
    spine = resolve_active_spine()
    if spine is None:
        return None
    return spine.append(
        execution_point=execution_point,
        channel=channel,
        caller_payload=payload,
        outcome=outcome,
    )


def emit_exception_caught(record: ExceptionRecordT) -> EventRecord | None:
    """异常捕获事件的唯一 emitter(SSOT)。

    接收 :class:`ExceptionRecord`,通过 ``record.asdict()`` 序列化
    payload,统一走 ``error`` channel + ``failure`` outcome。
    """
    payload = record.asdict()
    from lca.infrastructure.session._overflow_0.bindings import resolve_session_reader
    from lca.loop.fact_gateway import publish_ep_bound

    session = resolve_session_reader()
    if session is not None:
        publish_ep_bound(
            _EXECUTION_POINT,
            payload,
            session=session,
            actor=_EMIT_ACTOR,
        )
        return None
    return _safe_append(
        execution_point=_EXECUTION_POINT,
        channel=_CHANNEL_ERROR,
        payload=payload,
        outcome=_OUTCOME_FAILURE,
    )


__all__ = ["emit_exception_caught"]
