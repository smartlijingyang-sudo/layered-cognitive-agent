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
from pathlib import Path
from typing import Protocol, runtime_checkable

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink

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
        return iter(())


class FilePersistenceCoordinator:
    """包装 :class:`FileSink` 的持久化协同器。

    ``flush()``  → 调 sink 的 ``fsync``(通过 ``FileSink.close`` 不行 ——
    close 后不可再用;改为直接 flush sink 内部 fd)
    ``close()``  → 关 sink
    ``restore()`` → 从 events.jsonl 逐行读回 ``EventRecord``(仅支持 seq >= from_seq)

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
        """Checkpoint replay —— 当前返回空迭代器。

        完整实现需要 EventRecord 反序列化(由 PR-15 提供);
        本 PR 阶段仅占位,保证协议面可用。

        Parameters
        ----------
        from_seq:
            起始 sequence(含)。

        Yields
        ------
        EventRecord
            空迭代器。
        """
        _ = from_seq
        return iter(())


__all__ = [
    "FilePersistenceCoordinator",
    "NullPersistenceCoordinator",
    "PersistenceCoordinator",
]
