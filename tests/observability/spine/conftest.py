"""Shared fixtures for spine tests.

ADR-0186 后 ``spine_port_append`` 要求 Session hook 绑定。
为测试提供 ``sync_passthrough_hook`` fixture 模拟旧同步路径行为。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

import pytest

from lca.infrastructure.observability.loop_cursor._spine_port import (
    bind_session_append_hook,
    reset_session_append_hook,
)
from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.base import EventSink

log = logging.getLogger(__name__)


class SyncPassthroughHook:
    """测试用 passthrough hook:模拟旧同步路径行为。

    ADR-0186 后生产路径走 Session runtime;此 hook 为测试保留旧语义:
    stamp + write to sinks + notify subscribers。
    """

    def __call__(
        self,
        sinks: Sequence[EventSink],
        subscribers: Sequence[Callable[[EventRecord], None]],
        *,
        execution_point: str,
        channel: str,
        caller_payload: dict[str, Any] | None = None,
        outcome: Any | None = None,
        span_ctx: Any | None = None,
        phase: str = "live",
        reason: str | None = None,
        when: datetime | None = None,
        ref: Any = None,
    ) -> EventRecord:
        now = when or datetime.now()
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
            "sha256:"
            + hashlib.sha256(((prev_hash or "") + causality_id).encode("utf-8")).hexdigest()
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

        # FD-1: sinks fail-fast (let errors propagate)
        for sink in sinks:
            sink.write(record)

        SpineContext.chain_hash(new_hash)

        # FD-2: subscribers contained
        for fn in tuple(subscribers):
            try:
                fn(record)
            except Exception as exc:
                log.warning(
                    "spine.deriver_failed execution_point=%s err=%s",
                    record.execution_point,
                    exc,
                    exc_info=True,
                )

        return record


@pytest.fixture(autouse=True)
def sync_passthrough_hook():
    """自动绑定测试用 passthrough hook,测试结束后释放。

    autouse=True 使所有 spine 测试默认走旧同步路径语义。
    需要测试 Session hook 行为的测试可显式覆盖此 fixture。
    """
    token = bind_session_append_hook(SyncPassthroughHook())
    try:
        yield
    finally:
        reset_session_append_hook(token)
