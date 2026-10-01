"""Spine emission helpers for ``wrap_instrument``.

Every event emitted by the instrument wrapper funnels through the
helpers in this module. When an ``emit_pipeline`` is installed via
:func:`set_active_pipeline_accessor`, each event goes through
``EmitPipeline.emit(...)`` so enabled ``FieldProducer`` plugins
contribute their keys to ``EventRecord.payload``. With no pipeline
installed the wrapper falls back to a direct ``EventSpine.append(...)``,
keeping the PR-4 assembler contract intact for pre-boot and unit-test
paths.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.contracts.observability import (
    Channel,
    EventSpine,
    Outcome as OutcomeT,
    SpanContext,
    exc_to_record,
)
from lca.contracts.protocols.loop.spine_publish import is_session_ssot_hook_active
from lca.harness.declarative.compile.instrument.accessors import _resolve_pipeline

log = logging.getLogger(__name__)

# ``_TRACEBACK_CAPPED_BYTES`` mirrors ``_publish_i17_rejection`` (ADR-0165.1 §96).
# 4 KiB is enough to keep the most recent frames of a typical agent call while
# keeping the per-event jsonl cost bounded.
_TRACEBACK_CAPPED_BYTES = 4096


def _is_i17_violation(exc: BaseException) -> bool:
    """Duck-typed check for ``I17Violation`` without a static import.

    ``lca.harness`` must not statically import ``lca.plugins``. The
    I17 class lives in :mod:`lca.plugins.observability.spine.emit_pipeline`
    and is identifiable by its fully-qualified name. This lets the
    wrapper route I17 failures to a dedicated traceback-emitting path
    (the silent-swallow bug from ADR-2026-09-02-i17-traceback §A) while
    keeping the assembler import graph unchanged.
    """
    cls = type(exc)
    return cls.__name__ == "I17Violation" and cls.__module__ in (
        "lca.infrastructure.observability.spine.spine.enrich",
        "lca.plugins.observability.spine.emit_pipeline",
    )


def _exception_payload(exc: BaseException, *, boundary: str = "instrument_wrap") -> dict[str, Any]:
    """Structured failure fields —— 走 :func:`exc_to_record` SSOT。

    ADR-2026-09-02-i17-stream-align §B + ADR-0169: wrap 层的异常归一化
    必须与 transport 路径一致,都经过 :class:`ExceptionRecord`。
    历史 ``exc_type`` / ``reason`` legacy alias 由 :meth:`ExceptionRecord.asdict`
    提供,这里不再手搓。
    """
    return exc_to_record(exc, boundary=boundary).asdict()


def _emit_spine_direct(
    *,
    spine: EventSpine,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any],
    outcome: OutcomeT | None,
    span: SpanContext | None,
) -> None:
    """Direct ``EventSpine.append`` with contained failure handling."""
    try:
        spine.append(
            execution_point=execution_point,
            channel=channel,
            caller_payload=payload,
            outcome=outcome,
            span_ctx=span,
        )
    except ValueError as exc:
        log.warning(
            "wrap_instrument: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
            exc_info=True,
        )
    except Exception as exc:
        if _is_i17_violation(exc):
            _publish_i17_rejection(
                spine=spine,
                span=span,
                attempted_ep=execution_point,
                exc=exc,
                channel=channel,
            )
            log.error(
                "wrap_instrument: I17 rejected ep=%s reason=%s",
                execution_point,
                exc,
                exc_info=True,
            )
        else:
            log.warning(
                "wrap_instrument: spine emit failed ep=%s err=%s",
                execution_point,
                exc,
                exc_info=True,
            )


def _emit_via_pipeline(
    *,
    pipeline: Any,
    spine: EventSpine,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any],
    outcome: OutcomeT | None,
    span: SpanContext | None,
) -> None:
    """Route through ``EmitPipeline.emit`` with contained failure handling."""
    try:
        pipeline.emit(
            execution_point=execution_point,
            channel=channel,
            span_ctx=span,
            caller_payload=payload,
            spine=spine,
            outcome=outcome,
        )
    except ValueError as exc:
        log.warning(
            "wrap_instrument: drop invalid event ep=%s err=%s",
            execution_point,
            exc,
            exc_info=True,
        )
    except Exception as exc:
        if _is_i17_violation(exc):
            _publish_i17_rejection(
                spine=spine,
                span=span,
                attempted_ep=execution_point,
                exc=exc,
                channel=channel,
            )
            log.error(
                "wrap_instrument: I17 rejected ep=%s reason=%s",
                execution_point,
                exc,
                exc_info=True,
            )
        else:
            log.warning(
                "wrap_instrument: pipeline emit failed ep=%s err=%s",
                execution_point,
                exc,
                exc_info=True,
            )


def _safe_append(
    *,
    spine: EventSpine | None,
    execution_point: str,
    channel: Channel,
    payload: dict[str, Any],
    outcome: OutcomeT | None,
    span: SpanContext | None,
    exc: BaseException | None = None,
) -> None:
    """Emit a spine event without letting a broken helper block the caller.

    When a process-local EmitPipeline accessor is installed (PR-7.1),
    the emission is routed through it so enabled ``FieldProducer``
    plugins may merge their keys into the payload before the
    ``EventRecord`` is sealed — unless a production Session SSOT hook
    is active, in which case enrich/commit/anomaly already run at the
    Session boundary and the wrapper calls ``EventSpine.append`` directly.
    When no pipeline is installed this function falls back to the direct
    ``EventSpine.append`` path so PR-4 assembler contracts still hold
    under unit tests.

    ``exc`` carries a ``BaseException`` captured by the wrap layer at
    the call site. When provided it is merged into the payload as the
    structured failure fields documented in :func:`_exception_payload`,
    so a channel="error" event always carries enough information to
    render the traceback without re-raising.
    """
    if exc is not None:
        # Caller payload wins on conflict (the caller may override
        # ``exception_message`` with a domain-specific phrasing), so we
        # merge exc first and then apply caller payload on top.
        payload = {**_exception_payload(exc), **payload}
    if spine is None:
        return
    if is_session_ssot_hook_active():
        _emit_spine_direct(
            spine=spine,
            execution_point=execution_point,
            channel=channel,
            payload=payload,
            outcome=outcome,
            span=span,
        )
        return
    pipeline = _resolve_pipeline()
    if pipeline is not None:
        _emit_via_pipeline(
            pipeline=pipeline,
            spine=spine,
            execution_point=execution_point,
            channel=channel,
            payload=payload,
            outcome=outcome,
            span=span,
        )
        return
    _emit_spine_direct(
        spine=spine,
        execution_point=execution_point,
        channel=channel,
        payload=payload,
        outcome=outcome,
        span=span,
    )


def _publish_i17_rejection(
    *,
    spine: EventSpine,
    span: SpanContext | None,
    attempted_ep: str,
    exc: BaseException,
    channel: Channel,
) -> None:
    """Emit one ``spine.i17.rejected`` journal event with the original traceback.

    Mirrors ``EmitPipeline``'s sidecar style so the rejection is
    recoverable from the run directory (rather than only from
    stderr). Falls back to a ``log.warning`` when the spine itself
    rejects the publication — we never want reject-noticing to
    mask the original I17.
    """
    rec = exc_to_record(exc, boundary="spine.i17.rejection")
    try:
        spine.append(
            execution_point="spine.i17.rejected",
            channel="error",
            caller_payload={
                "attempted_execution_point": attempted_ep,
                "exception_class": rec.exception_class,
                "reason": rec.exception_message,
                "err_kind": rec.err_kind.value,
                "traceback_text": rec.traceback_text,
                "span_id": getattr(span, "span_id", None),
                "outer_channel": str(channel),
            },
            outcome="failure",
            span_ctx=span,
        )
    except Exception as publish_exc:
        log.warning(
            "wrap_instrument: spine.i17.rejected publication failed "
            "err=%s; I17 traceback still on stderr",
            publish_exc,
            exc_info=True,
        )


__all__ = [
    "_TRACEBACK_CAPPED_BYTES",
    "_emit_spine_direct",
    "_emit_via_pipeline",
    "_exception_payload",
    "_is_i17_violation",
    "_publish_i17_rejection",
    "_safe_append",
]
