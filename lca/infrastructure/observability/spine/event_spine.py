"""EventSpine — single entrypoint for emitting events (I4 / I5).

All callers go through ``spine.append(...)``. Direct calls to legacy
``RunStore.append`` etc. are forbidden at runtime by I4.

FD-1 sink errors propagate to caller (fail-fast).
FD-2 deriver errors are contained: a logged spine.deriver_failed event
       is emitted; the original event still reaches the sink.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import (
    Channel,
    EventRecord,
    Outcome,
    Phase,
)
from lca.infrastructure.observability.spine.sinks.base import EventSink

log = logging.getLogger(__name__)


class EventSpine:
    """The single append-only entrypoint for framework events."""

    def __init__(
        self,
        sinks: list[EventSink],
        *,
        subscribers: list[Callable[[EventRecord], None]] | None = None,
        run_id: str | None = None,
    ) -> None:
        if not sinks:
            raise ValueError("EventSpine requires at least one sink")
        self._sinks = sinks
        self._subscribers = list(subscribers or [])
        if run_id is not None:
            SpineContext.set_run(run_id)

    def subscribe(self, fn: Callable[[EventRecord], None]) -> Callable[[], None]:
        """Register a deriver / callback. Returns disposer."""
        self._subscribers.append(fn)

        def _dispose() -> None:
            with suppress(ValueError):
                self._subscribers.remove(fn)

        return _dispose

    def append(
        self,
        *,
        execution_point: str,
        channel: Channel,
        caller_payload: dict[str, Any] | None = None,
        outcome: Outcome | None = None,
        span_ctx: Any | None = None,
        phase: Phase = "live",
        reason: str | None = None,
        when: datetime | None = None,
    ) -> EventRecord:
        """Stamp and dispatch an event to all sinks (FD-1) and subscribers (FD-2)."""

        now = when or datetime.now(timezone.utc)
        seq = SpineContext.next_sequence()
        epoch = SpineContext.next_epoch()
        parent_id = (
            span_ctx.parent_span_id
            if span_ctx is not None
            else (SpineContext.current_span().span_id if SpineContext.current_span() else None)
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
            "sha256:"
            + hashlib.sha256(((prev_hash or "") + causality_id).encode("utf-8")).hexdigest()
        )

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
            when_corrected=now,
            prev_event_hash=prev_hash,
            run_id=run_id,
            step_id=step_id,
            payload=caller_payload or {},
            phase=phase,
            reason=reason,
        )

        # FD-1: sinks fail-fast; first error propagates
        for sink in self._sinks:
            sink.write(record)

        SpineContext.chain_hash(new_hash)

        # FD-2: subscribers contained; failures logged, never propagated
        for fn in tuple(self._subscribers):
            try:
                fn(record)
            except Exception as exc:
                log.warning(
                    "spine.deriver_failed execution_point=%s deriver=%s err=%s",
                    record.execution_point,
                    getattr(fn, "__qualname__", repr(fn)),
                    exc,
                    exc_info=True,
                )

        return record

    def flush(self) -> None:
        for sink in self._sinks:
            close = getattr(sink, "flush", None)
            if callable(close):
                close()

    def close(self) -> None:
        for sink in self._sinks:
            sink.close()
