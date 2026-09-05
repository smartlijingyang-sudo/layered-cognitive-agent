"""EventSpine.append → Session SSOT 转发钩子（ADR-0186 PR-3h 生产接线）。

``bind_session_append_hook`` 在 run bind 时安装本模块产出的
:class:`SessionAppendHook`，使 ``EmitPipeline.emit`` /
``wrap_instrument`` 等仍调用 ``EventSpine.append`` 的路径统一落
``Session.append``，不再双写 FileSink。

FieldProducer merge + I17 在 hook 内经 :mod:`spine_enrich` 执行（wave 2）。
保留 :class:`EventRecord` stamping 供 anomaly 等 in-process 消费者。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from lca.infrastructure.observability.loop_cursor._spine_port import (
    SessionAppendHook,
    SESSION_SSOT_HOOK_MARKER,
    bind_session_append_hook,
    reset_session_append_hook,
)
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import Channel, EventRecord, Outcome, Phase
from lca.infrastructure.observability.spine.sinks.base import EventSink
from lca.plugins.observability.spine.spine_enrich import get_active_spine_enricher
from lca.plugins.session.runtime.bind import RunEventSessionBridge
from lca_kernel.events.payloads_spine import SpineEventPayload

_log = logging.getLogger(__name__)

_NO_PRODUCER = object()

__all__ = [
    "SESSION_SSOT_HOOK_MARKER",
    "bind_bridge_spine_hook",
    "make_session_spine_append_hook",
    "reset_bridge_spine_hook",
]


def _stamp_event_record(
    *,
    execution_point: str,
    channel: Channel,
    caller_payload: dict[str, Any] | None,
    outcome: Outcome | None,
    span_ctx: Any | None,
    phase: Phase,
    reason: str | None,
    when: datetime | None,
    ref: Any,
) -> EventRecord:
    """Stamp in-process EventRecord without writing EventSpine sinks."""
    now = when or datetime.now(UTC)
    seq = SpineContext.next_sequence()
    epoch = SpineContext.next_epoch()
    current_span = SpineContext.current_span()
    parent_id = (
        span_ctx.parent_span_id
        if span_ctx is not None
        else (current_span.span_id if current_span is not None else None)
    )
    span_id = span_ctx.span_id if span_ctx is not None else f"lca-seq-{seq:08x}"
    run_id = SpineContext.get_run() or "default-run"
    step_id = SpineContext.get_step()
    prev_hash = SpineContext.last_hash()
    causality_payload = json.dumps(
        {
            "execution_point": execution_point,
            "channel": channel,
            "payload": caller_payload or {},
            "span_id": span_id,
            "epoch": epoch,
        },
        sort_keys=True,
        default=str,
    )
    causality_id = "sha256:" + hashlib.sha256(causality_payload.encode()).hexdigest()
    new_hash = (
        "sha256:" + hashlib.sha256(((prev_hash or "") + causality_id).encode("utf-8")).hexdigest()
    )

    _ref_trace_id = getattr(ref, "trace_id", None) if ref is not None else None
    _payload_trace_id = (caller_payload or {}).get("trace_id")
    if _ref_trace_id is not None:
        resolved_trace_id: str | None = _ref_trace_id
    elif _payload_trace_id is not None:
        resolved_trace_id = str(_payload_trace_id)
    else:
        resolved_trace_id = SpineContext.get_trace_id()

    record = EventRecord(
        execution_point=execution_point,
        channel=channel,
        span_id=span_id,
        parent_span_id=parent_id,
        sequence=seq,
        epoch=epoch,
        causality_id=causality_id,
        outcome=outcome,
        when=now,
        trace_id=resolved_trace_id,
        when_corrected=now,
        prev_event_hash=prev_hash,
        run_id=run_id,
        step_id=step_id,
        payload=caller_payload or {},
        phase=phase,
        reason=reason,
    )
    SpineContext.chain_hash(new_hash)
    return record


def _publish_producer_failures(
    bridge: RunEventSessionBridge,
    *,
    producer_failures: list[tuple[Any, dict[str, Any]]],
    outer_execution_point: str,
    span_ctx: Any | None,
    phase: Phase,
) -> None:
    for producer_origin, entry in producer_failures:
        try:
            bridge.append(
                SpineEventPayload(
                    execution_point="spine.producer.failure",
                    channel="error",
                    payload={
                        "producer": getattr(producer_origin, "name", "unknown"),
                        "key": entry.get("key"),
                        "exception_class": entry.get("exception_class"),
                        "traceback_text": entry.get("traceback_text"),
                        "span_id": getattr(span_ctx, "span_id", None),
                        "outer_execution_point": outer_execution_point,
                    },
                ),
                producer=_NO_PRODUCER,
            )
        except Exception as exc:
            _log.warning(
                "spine_hook: spine.producer.failure publication failed err=%s",
                exc,
                exc_info=True,
            )


def make_session_spine_append_hook(bridge: RunEventSessionBridge) -> SessionAppendHook:
    """Build a hook that enriches then commits spine-shaped writes via ``bridge``."""

    def hook(
        sinks: Sequence[EventSink],
        subscribers: Sequence[Callable[[EventRecord], None]],
        *,
        execution_point: str,
        channel: Channel,
        caller_payload: dict[str, Any] | None = None,
        outcome: Outcome | None = None,
        span_ctx: Any | None = None,
        phase: Phase = "live",
        reason: str | None = None,
        when: datetime | None = None,
        ref: Any = None,
    ) -> EventRecord:
        del sinks, subscribers

        enricher = get_active_spine_enricher()
        if enricher is not None:
            enrich_result = enricher(
                execution_point=execution_point,
                channel=channel,
                caller_payload=caller_payload,
                span_ctx=span_ctx,
            )
            payload_data = enrich_result.merged
            producer_failures = enrich_result.producer_failures
        else:
            payload_data = dict(caller_payload or {})
            producer_failures = []

        bridge.append(
            SpineEventPayload(
                execution_point=execution_point,
                channel=channel,
                payload=payload_data,
            ),
            producer=_NO_PRODUCER,
        )
        if producer_failures:
            _publish_producer_failures(
                bridge,
                producer_failures=producer_failures,
                outer_execution_point=execution_point,
                span_ctx=span_ctx,
                phase=phase,
            )

        return _stamp_event_record(
            execution_point=execution_point,
            channel=channel,
            caller_payload=payload_data,
            outcome=outcome,
            span_ctx=span_ctx,
            phase=phase,
            reason=reason,
            when=when,
            ref=ref,
        )

    return _mark_session_ssot_hook(hook)


def _mark_session_ssot_hook(hook: SessionAppendHook) -> SessionAppendHook:
    setattr(hook, SESSION_SSOT_HOOK_MARKER, True)
    return hook


def bind_bridge_spine_hook(bridge: RunEventSessionBridge) -> Any:
    """Install process-local spine→Session hook for one run bridge."""
    return bind_session_append_hook(make_session_spine_append_hook(bridge))


def reset_bridge_spine_hook(token: Any) -> None:
    """Reset hook installed by :func:`bind_bridge_spine_hook`."""
    reset_session_append_hook(token)
