"""spine_file_sink plugin 实现（ADR-0181 PR-8）。

# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# shim：保留旧 FileSink 逻辑（<run_dir>/<run_id>.spine.jsonl + exceptions 索引）
# 但改用 EventMechanism callback 入口（``__call__(payload, ref)``）替代
# 旧 ``write(EventRecord)``。EventRecord 字段从 SpineEventPayload + EventRef
# 推导，保持链上字节兼容。

PR-9 旧 spine 全退役时一并删除本 shim（rg FileSink lca/infrastructure/
= 0 触发）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lca_kernel.events.mechanism import EventRef
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.spine_runtime import is_spine_event

# Reuse the OLD FileSink implementation; only the entry point changes.
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink

log = logging.getLogger(__name__)


class SpineFileSink:
    """EventMechanism-aware wrapper around the old FileSink.

    Subscribes to all spine EP categories and forwards as ``EventRecord``
    to the underlying ``FileSink.write`` method. The byte format on
    disk is unchanged (same field schema).
    """

    def __init__(self, run_dir: Path | None = None) -> None:
        # FileSink.__init__ requires run_dir + run_id; default to cwd + sentinel
        target = run_dir or Path.cwd()
        self._inner = FileSink(run_dir=target, run_id="default-run")

    def __call__(self, payload: Any, ref: EventRef) -> None:
        if not is_spine_event(payload):
            raise TypeError(
                f"SpineFileSink 只接 SpineEventPayload；got {type(payload).__name__}"
            )
        sp: SpineEventPayload = payload  # narrow for type checker
        record = self._build_event_record(sp, ref)
        self._inner.write(record)

    def _build_event_record(
        self, sp: SpineEventPayload, ref: EventRef
    ) -> Any:
        """推导旧 EventRecord（保持磁盘兼容）。"""
        from lca.infrastructure.observability.spine.event_record import (
            Channel,
            EventRecord,
            Outcome,
        )

        channel_str = sp.channel
        try:
            channel = Channel(channel_str)
        except ValueError:
            channel = Channel.FACT  # fallback
        outcome_str = sp.payload.get("outcome", "success")
        try:
            outcome = Outcome(outcome_str)
        except ValueError:
            outcome = Outcome.SUCCESS
        return EventRecord(
            event_id=ref.event_id,
            execution_point=sp.execution_point,
            channel=channel,
            outcome=outcome,
            caller_payload=dict(sp.payload),
            timestamp=ref.ts,
        )

    def flush(self) -> None:
        self._inner.flush()

    def close(self) -> None:
        self._inner.close()


__all__ = ["SpineFileSink"]
