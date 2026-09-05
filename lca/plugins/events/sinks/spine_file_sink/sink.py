"""spine_file_sink plugin 实现（ADR-0181 PR-8 shim → ADR-0186 write-behind）。

生产路径不再逐条 ``SpineSink.open/append/close``;委托
:class:`PersistenceObserver` enqueue 到 :class:`RunWriteBehindRegistry`。
``exception.caught`` 索引由 :mod:`exception_index_writer` 独立 observer 负责。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca.infrastructure.persistence.run_buffer_registry import RunWriteBehindRegistry
from lca.infrastructure.persistence.run_paths import run_id_from_event_id
from lca_kernel.events.persistence import PersistenceObserver
from lca_kernel.events.spine_runtime import is_spine_event

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef
    from lca_kernel.events.spine_runtime import SpineEventRecord

_run_id_of = run_id_from_event_id


class SpineFileSink:
    """Session.observe 落盘 shim —— 委托 PersistenceObserver write-behind。"""

    def __init__(
        self,
        run_dir: Path | None = None,
        *,
        observer: PersistenceObserver | None = None,
        registry: RunWriteBehindRegistry | None = None,
    ) -> None:
        self._run_dir = run_dir
        self._closed = False
        self._observer = observer or PersistenceObserver(
            run_dir=run_dir,
            registry=registry or RunWriteBehindRegistry.default(),
        )

    def __call__(self, payload: Any, ref: EventRef) -> None:
        if self._closed:
            raise RuntimeError("SpineFileSink 已关闭，不可 append")
        if not is_spine_event(payload):
            raise TypeError(f"SpineFileSink 只接 SpineEventPayload；got {type(payload).__name__}")
        _run_id_of(ref.event_id)
        self._observer.on_session_event(payload, ref)

    def append(self, record: SpineEventRecord) -> None:
        if self._closed:
            raise RuntimeError("SpineFileSink 已关闭，不可 append")
        run_id = _run_id_of(record.event_id)
        self._observer.enqueue_spine_record(record)
        self._observer.flush_sync(run_id)

    def flush(self) -> None:
        if self._closed:
            raise RuntimeError("SpineFileSink 已关闭，不可 flush")
        self._observer.flush_sync()

    def close(self) -> None:
        self._closed = True


__all__ = ["SpineFileSink", "_run_id_of"]
