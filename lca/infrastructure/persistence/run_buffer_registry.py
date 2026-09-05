"""Per-run write-behind buffers for Session durable observers (ADR-0186 §4.2).

``Session.append`` observers enqueue into in-memory ``WriteBehindBuffer``
instances; ``Session.flush()`` / run unbind drain to ``JsonlFileSink``.
No observer performs direct per-event ``open/write/fsync``.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from lca.contracts.observability.fsync import FsyncProtocol
from lca.infrastructure.persistence.jsonl_sink import JsonlFileSink
from lca.infrastructure.persistence.run_paths import (
    exceptions_path_for_run,
    run_id_from_event_id,
    spine_path_for_run,
)
from lca.infrastructure.persistence.write_behind import WriteBehindBuffer

if TYPE_CHECKING:
    from lca_kernel.events.session import SessionProtocol
    from lca_kernel.events.spine_runtime import SpineEventRecord

log = logging.getLogger(__name__)

_DEFAULT_SPINE_DELAY_MS = 50
_DEFAULT_EXCEPTIONS_DELAY_MS = 200


@dataclass(frozen=True, slots=True)
class _SpineQueuedRecord:
    record: SpineEventRecord
    event_id: str


class _SpineBatchSink:
    """Write-behind target: batch of spine records → one JSONL append + fsync."""

    def __init__(
        self,
        path: Path,
        *,
        fsync: bool,
        on_batch_written: Callable[[Sequence[str]], None],
    ) -> None:
        self._inner = JsonlFileSink(
            path,
            fsync=fsync,
            sort_keys=True,
            serializer=_serialize_spine_record,
        )
        self._on_batch_written = on_batch_written

    def append_batch(self, events: Sequence[_SpineQueuedRecord]) -> None:
        if not events:
            return
        self._inner.append_batch([item.record for item in events])
        self._on_batch_written([item.event_id for item in events])

    def close(self) -> None:
        self._inner.close()


class _DictBatchSink:
    """Write-behind target for exception index lines (plain dict rows)."""

    def __init__(
        self,
        path: Path,
        *,
        fsync: bool,
    ) -> None:
        self._inner = JsonlFileSink(path, fsync=fsync, sort_keys=True)

    def append_batch(self, events: Sequence[dict[str, Any]]) -> None:
        self._inner.append_batch(events)

    def close(self) -> None:
        self._inner.close()


def _serialize_spine_record(record: SpineEventRecord) -> dict[str, Any]:
    return record.to_dict()


@dataclass
class _RunPersistenceState:
    run_id: str
    run_dir: Path | None
    spine_buffer: WriteBehindBuffer
    exceptions_buffer: WriteBehindBuffer
    spine_fsync: bool
    exceptions_fsync: bool


class RunWriteBehindRegistry:
    """Process-level registry: ``run_id`` → spine + exceptions write-behind buffers."""

    _default_instance: ClassVar[RunWriteBehindRegistry | None] = None

    def __init__(
        self,
        *,
        spine_fsync_policy: FsyncProtocol = FsyncProtocol.BATCH,
        spine_fsync_interval_ms: int = _DEFAULT_SPINE_DELAY_MS,
        exceptions_fsync_policy: FsyncProtocol = FsyncProtocol.COMMIT,
        on_spine_batch_written: Callable[[Sequence[str]], None] | None = None,
    ) -> None:
        self._spine_fsync_policy = spine_fsync_policy
        self._spine_fsync_interval_ms = spine_fsync_interval_ms
        self._exceptions_fsync_policy = exceptions_fsync_policy
        self._on_spine_batch_written = on_spine_batch_written
        self._runs: dict[str, _RunPersistenceState] = {}
        self._lock = threading.Lock()
        self._last_flush_ms: int | None = None
        self._written_total = 0

    @classmethod
    def default(cls) -> RunWriteBehindRegistry:
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    @classmethod
    def set_default(cls, instance: RunWriteBehindRegistry | None) -> None:
        cls._default_instance = instance

    @classmethod
    def reset_singleton(cls) -> None:
        cls._default_instance = None

    @property
    def last_flush_ms(self) -> int | None:
        return self._last_flush_ms

    @property
    def written_total(self) -> int:
        return self._written_total

    def pending_count(self) -> int:
        with self._lock:
            return sum(
                state.spine_buffer.pending_count + state.exceptions_buffer.pending_count
                for state in self._runs.values()
            )

    def pending_count_for_run(self, run_id: str) -> int:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None:
                return 0
            return state.spine_buffer.pending_count + state.exceptions_buffer.pending_count

    def enqueue_spine(
        self,
        record: SpineEventRecord,
        *,
        run_dir: Path | None = None,
    ) -> str:
        """Enqueue one spine record; returns ``event_id``."""
        event_id = record.event_id
        run_id = run_id_from_event_id(event_id)
        state = self._state_for(run_id, run_dir=run_dir)
        state.spine_buffer.enqueue(_SpineQueuedRecord(record=record, event_id=event_id))
        if self._spine_fsync_policy is FsyncProtocol.PER_WRITE:
            self.flush_run(run_id)
        return event_id

    def enqueue_exception_line(
        self,
        event_id: str,
        line: dict[str, Any],
        *,
        run_dir: Path | None = None,
    ) -> None:
        run_id = run_id_from_event_id(event_id)
        state = self._state_for(run_id, run_dir=run_dir)
        state.exceptions_buffer.enqueue(line)
        if self._exceptions_fsync_policy is FsyncProtocol.PER_WRITE:
            self.flush_run(run_id)

    def flush_run(self, run_id: str) -> None:
        with self._lock:
            state = self._runs.get(run_id)
        if state is None:
            return
        state.spine_buffer.flush()
        state.exceptions_buffer.flush()
        self._last_flush_ms = int(time.time() * 1000)

    def dispose_run(self, run_id: str) -> None:
        with self._lock:
            state = self._runs.pop(run_id, None)
        if state is None:
            return
        state.spine_buffer.dispose()
        state.exceptions_buffer.dispose()
        self._last_flush_ms = int(time.time() * 1000)

    def flush_all(self) -> None:
        with self._lock:
            run_ids = list(self._runs)
        for run_id in run_ids:
            self.flush_run(run_id)

    def dispose_all(self) -> None:
        with self._lock:
            run_ids = list(self._runs)
        for run_id in run_ids:
            self.dispose_run(run_id)

    def _state_for(self, run_id: str, *, run_dir: Path | None) -> _RunPersistenceState:
        with self._lock:
            existing = self._runs.get(run_id)
            if existing is not None:
                if run_dir is not None and existing.run_dir != run_dir:
                    existing.run_dir = run_dir
                return existing
            state = self._create_state(run_id, run_dir=run_dir)
            self._runs[run_id] = state
            return state

    def _create_state(self, run_id: str, *, run_dir: Path | None) -> _RunPersistenceState:
        spine_path = spine_path_for_run(run_id, run_dir=run_dir)
        exceptions_path = exceptions_path_for_run(run_id, run_dir=run_dir)
        spine_path.parent.mkdir(parents=True, exist_ok=True)
        exceptions_path.parent.mkdir(parents=True, exist_ok=True)

        spine_fsync = self._spine_fsync_policy is not FsyncProtocol.COMMIT
        exceptions_fsync = self._exceptions_fsync_policy is FsyncProtocol.PER_WRITE

        def _on_batch_written(event_ids: Sequence[str]) -> None:
            self._written_total += len(event_ids)
            if self._on_spine_batch_written is not None:
                self._on_spine_batch_written(event_ids)

        spine_sink = _SpineBatchSink(
            spine_path,
            fsync=spine_fsync,
            on_batch_written=_on_batch_written,
        )
        exceptions_sink = _DictBatchSink(exceptions_path, fsync=exceptions_fsync)

        spine_delay = (
            1
            if self._spine_fsync_policy is FsyncProtocol.PER_WRITE
            else self._spine_fsync_interval_ms
        )
        exceptions_delay = (
            1
            if self._exceptions_fsync_policy is FsyncProtocol.PER_WRITE
            else _DEFAULT_EXCEPTIONS_DELAY_MS
        )

        return _RunPersistenceState(
            run_id=run_id,
            run_dir=run_dir,
            spine_buffer=WriteBehindBuffer(
                spine_sink,
                max_delay_ms=spine_delay,
                on_failure=lambda exc, rid=run_id: log.error(
                    "run_buffer_registry: spine batch write failed run_id=%s err=%s",
                    rid,
                    exc,
                ),
            ),
            exceptions_buffer=WriteBehindBuffer(
                exceptions_sink,
                max_delay_ms=exceptions_delay,
                on_failure=lambda exc, rid=run_id: log.error(
                    "run_buffer_registry: exceptions batch write failed run_id=%s err=%s",
                    rid,
                    exc,
                ),
            ),
            spine_fsync=spine_fsync,
            exceptions_fsync=exceptions_fsync,
        )


class SessionPersistenceFlushListener:
    """``Session.register_flush_listener`` hook: drain run write-behind buffers."""

    async def flush(self, session: SessionProtocol) -> None:
        RunWriteBehindRegistry.default().flush_run(session.id)


__all__ = [
    "RunWriteBehindRegistry",
    "SessionPersistenceFlushListener",
]
