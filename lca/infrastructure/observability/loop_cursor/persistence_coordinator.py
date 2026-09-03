"""PersistenceCoordinator —— 持久化协同器(ADR-0169 D8 / §D5)。

职责:
- ``flush()``    —— 通知 sink 刷盘(由 CloseBarrier 在 L7-3a 调用)
- ``close()``    —— 关闭底层 sink 资源
- ``restore(from_seq) -> Iterator[EventRecord]`` —— checkpoint replay
  从 ``from_seq`` 开始回放事件(由 halt-resume / checkpoint 路径调用)

五缝之一(ADR-0169 D8):LoopCursor(控制) / ProjectionHost(投影) /
**PersistenceCoordinator(持久化)** / ModelVisibleCapture(边界) / CloseBarrier(关闭)。
cursor 不持本组件实例 —— 由 ObservabilityRuntime 持有,
由 CloseBarrier 协调 flush 顺序。

三种实现:
- :class:`PersistenceCoordinator`(Protocol) —— 契约
- :class:`NullPersistenceCoordinator`          —— no-op flush/close,restore 返回空
- :class:`FilePersistenceCoordinator`          —— 包装 :class:`FileSink`
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


@dataclass(frozen=True)
class PersistenceStats:
    """持久化协同器运行时统计(ADR-0169 PR-25 S3 装配)。"""

    total_appended: int
    last_seq: int
    bytes_written: int

    @classmethod
    def unavailable(cls, *, bytes_written: int = 0) -> PersistenceStats:
        """Marker factory — used by persistence backends that don't track counters.

        ``total_appended`` and ``last_seq`` are explicitly set to a
        sentinel (``-1``) to signal "sink did not record these"; this
        is louder than silently returning zeros that look like real
        measurements.  Callers that consume stats() should treat ``-1``
        as a documented absence marker rather than a real count.
        """
        return cls(total_appended=-1, last_seq=-1, bytes_written=bytes_written)

    @classmethod
    def zero(cls) -> PersistenceStats:
        """Deprecated — use :meth:`unavailable` for backends lacking counters."""
        return cls(total_appended=-1, last_seq=-1, bytes_written=0)


log = logging.getLogger(__name__)


@runtime_checkable
class PersistenceCoordinator(Protocol):
    """持久化协同器协议(ADR-0169 D8)。

    由 :class:`CloseBarrier` 在 L7-3a 调用 ``flush()``;
    由 checkpoint replay 路径调 ``restore(from_seq)``;
    由 runtime shutdown 调 ``close()``。
    """

    def flush(self) -> None:
        """通知 sink 刷盘(ADR-0169 D5 step 3a)。"""
        ...

    def close(self) -> None:
        """关闭底层 sink 资源(ADR-0169 D5 step 5)。"""
        ...

    def restore(self, from_seq: int) -> Iterator[EventRecord]:
        """从 ``from_seq`` 开始回放事件(checkpoint replay)。

        Parameters
        ----------
        from_seq:
            起始 sequence(含);回放 ``seq >= from_seq`` 的事件。

        Returns
        -------
        Iterator[EventRecord]
            按 seq 升序的事件迭代器;空迭代器表示无可回放事件。
        """
        _ = from_seq  # noqa: F841 — part of the public Protocol surface
        ...

    def stats(self) -> PersistenceStats:
        """运行时统计(总追加数 / 最后 seq / 写入字节)。"""
        ...


class NullPersistenceCoordinator:
    """No-op 持久化协同器(测试 / 无持久化场景)。

    ``flush()`` / ``close()`` 是空操作;``restore()`` 返回空迭代器。
    用于 ``ObservabilityRuntime`` 在调用方未提供 persistence 时的 fallback,
    或纯内存 cursor 场景。
    """

    def flush(self) -> None:
        """No-op。"""
        return None

    def close(self) -> None:
        """No-op。"""
        return None

    def restore(self, from_seq: int) -> Iterator[EventRecord]:
        """返回空迭代器。"""
        _ = from_seq  # noqa: F841 — null-coordinator ignores the input
        return iter(())

    def stats(self) -> PersistenceStats:
        """Null 永远返回零统计。"""
        return PersistenceStats.zero()


class FilePersistenceCoordinator:
    """包装 :class:`FileSink` 的持久化协同器。

    ``flush()``  → 调 sink 的 ``fsync``(通过 ``FileSink.close`` 不行 ——
    close 后不可再用;改为直接 flush sink 内部 fd)
    ``close()``  → 关 sink
    ``restore()`` → 从 spine ledger 逐行读回 ``EventRecord``(仅支持 seq >= from_seq)

    当前 ``restore()`` 返回空迭代器 —— FileSink 是 append-only JSONL,
    反向解析需要 ``EventRecord`` 反序列化器(由 PR-15 提供)。
    本 PR 阶段 restore 是占位;checkpoint replay 在 PR-5 才启用。

    Parameters
    ----------
    sink:
        被包装的 :class:`FileSink` 实例;本协调器不构造 sink(由调用方注入)。
    """

    def __init__(self, *, sink: FileSink) -> None:
        self._sink = sink

    @property
    def sink(self) -> FileSink:
        """暴露内部 sink(供 CloseBarrier / 测试读取路径)。"""
        return self._sink

    @property
    def path(self) -> Path:
        """sink 对应的文件路径。"""
        return self._sink.path

    def flush(self) -> None:
        """通过 FileSink 的 fd 调 fsync(不关闭文件描述符)。"""
        try:
            flush_method = getattr(self._sink, "flush", None)
            if callable(flush_method):
                flush_method()
            else:
                # FileSink 无显式 flush —— 调 fsync 但不 close
                fd = getattr(self._sink, "_fd", None)
                if fd is not None and not getattr(self._sink, "_closed", True):
                    import os

                    os.fsync(fd)
        except Exception as exc:
            log.warning("FilePersistenceCoordinator.flush failed: %s", exc, exc_info=True)

    def close(self) -> None:
        """关闭 sink。"""
        self._sink.close()

    def restore(self, from_seq: int) -> Iterator[EventRecord]:
        """Checkpoint replay —— fails loud.

        Full implementation needs ``EventRecord`` deserialization
        (delivered by PR-15 of ADR-0169). Until then we **raise**
        :class:`PersistenceRestoreUnavailableError` rather than
        silently yielding an empty iterator, so callers that genuinely
        need checkpoint replay either pin to a backend that supports
        it or fail fast at startup rather than discovering the gap at
        recovery time.

        Parameters
        ----------
        from_seq:
            起始 sequence(含)。

        Raises
        ------
        PersistenceRestoreUnavailableError
            Always — checkpoint replay from a file sink is not
            implemented. ADR-0169 PR-15 will replace this with a
            real ``EventRecord`` reader.
        """
        _ = from_seq  # noqa: F841 — referenced for documentation only
        raise PersistenceRestoreUnavailableError(
            "FilePersistenceCoordinator.restore is not implemented; "
            "checkpoint replay is delivered by ADR-0169 PR-15."
        )

    def stats(self) -> PersistenceStats:
        """File-sink stats.

        Returns the sink's path size as ``bytes_written`` (the only
        count a file sink exposes cheaply); ``total_appended`` and
        ``last_seq`` are explicit absence markers (-1) until the sink
        emits them. Consumers should treat ``-1`` as "not measured".
        """
        try:
            bytes_written = self._sink.path.stat().st_size
        except OSError:
            bytes_written = 0
        return PersistenceStats.unavailable(bytes_written=bytes_written)


class PersistenceRestoreUnavailableError(NotImplementedError):
    """Raised by :meth:`FilePersistenceCoordinator.restore`.

    Loud signal that the file-sink backend does not implement
    checkpoint replay (ADR-0169 PR-15). Use :class:`NullPersistenceCoordinator`
    if you want a benign empty iterator.
    """


__all__ = [
    "FilePersistenceCoordinator",
    "NullPersistenceCoordinator",
    "PersistenceCoordinator",
    "PersistenceRestoreUnavailableError",
    "PersistenceStats",
]
