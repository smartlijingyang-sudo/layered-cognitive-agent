"""Write-behind 批量写入缓冲区 —— Session persistence 内部基础设施。

对齐 DSH ``SessionWriteBehind`` 的核心语义：

1. ``enqueue`` 把事件拷贝进内存 pending buffer，首条事件触发定时窗口
2. 定时窗口到期或显式 ``flush()`` 时，批量写入 ``WriteBehindSink``
3. 写入失败 → 事件放回 pending（不丢失），标记暂停等待下次触发
4. ``dispose()`` 排空全部待写事件后关闭 sink

ADR-0186: 本模块是 Session persistence 的内部基础设施，由
``FilesystemJournalStore`` 消费。不接受新的直接调用方——持久化统一
经 Session observer 链（SpineFileSink / WriteBehindBuffer）落盘。

投递保证（对齐 Manus 指南 L0/L1/L2 + ``EventDurability``）：

- ``REQUIRED``：永不丢弃，写入失败必须保留重试
- ``BEST_EFFORT``：buffer 达到 ``max_buffer_size`` 时可丢弃最旧事件，
  聚合丢弃计数记入 ``dropped_count``

线程安全：所有公共方法通过 ``threading.Lock`` 保护。
"""

from __future__ import annotations

import contextlib
import copy
import threading
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class DropPolicy(StrEnum):
    """buffer 满时的丢弃策略。"""

    NEVER = "never"
    """永不丢弃（用于 REQUIRED 事件）。"""

    OLDEST_FIRST = "oldest_first"
    """丢弃最旧事件腾出空间（用于 BEST_EFFORT 事件）。"""

    NEWEST = "newest"
    """丢弃新入队事件（保留已有事件）。"""


@runtime_checkable
class WriteBehindSink(Protocol):
    """批量写入目标 —— 文件、数据库、远端服务等。

    实现要点：
    - ``append_batch`` 接收一个不可变序列，一次调用完成整批持久化
    - 单次调用内只做一次 fsync（不是每条一次）
    - ``close()`` 幂等，重复调用安全
    """

    def append_batch(self, events: Sequence[Any]) -> None:
        """持久化一批事件；失败抛异常（调用方负责保留重试）。"""

    def close(self) -> None:
        """关闭底层资源；幂等。"""


class WriteBehindBuffer:
    """有界的 write-behind 批量缓冲区。

    生命周期：

    1. 构造时传入 ``WriteBehindSink`` + 调度参数
    2. ``enqueue()`` 接收事件，拷贝入 pending，首条触发定时器
    3. 定时器到期 / ``flush()`` → 批量写 → 成功清空 / 失败保留
    4. ``dispose()`` → 最终 ``flush()`` + ``sink.close()``

    参数：
    - ``sink``：批量写入目标
    - ``max_delay_ms``：空闲队列收到首条事件后的最大等待时间（默认 200）
    - ``max_buffer_size``：pending buffer 上限（0 = 无限制）
    - ``drop_policy``：buffer 满时的丢弃策略
    - ``on_failure``：写入失败回调（日志 / 计数 / 告警）
    """

    def __init__(
        self,
        sink: WriteBehindSink,
        *,
        max_delay_ms: int = 200,
        max_buffer_size: int = 0,
        drop_policy: DropPolicy = DropPolicy.NEVER,
        on_failure: Callable[[Exception], None] | None = None,
    ) -> None:
        if max_delay_ms < 1:
            raise ValueError(f"max_delay_ms must be >= 1, got {max_delay_ms}")
        if max_buffer_size < 0:
            raise ValueError(f"max_buffer_size must be >= 0, got {max_buffer_size}")
        self._sink = sink
        self._max_delay_s = max_delay_ms / 1000.0
        self._max_buffer_size = max_buffer_size
        self._drop_policy = drop_policy
        self._on_failure = on_failure

        self._pending: list[Any] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._active_write = False
        self._paused = False
        self._closed = False
        self._dropped_count = 0
        self._failure_count = 0

    # ── 状态查询 ──────────────────────────────────────────────

    @property
    def pending_count(self) -> int:
        """当前待写事件数。"""
        with self._lock:
            return len(self._pending)

    @property
    def dropped_count(self) -> int:
        """因背压被丢弃的事件总数。"""
        with self._lock:
            return self._dropped_count

    @property
    def failure_count(self) -> int:
        """写入失败次数。"""
        with self._lock:
            return self._failure_count

    @property
    def is_closed(self) -> bool:
        with self._lock:
            return self._closed

    # ── 核心操作 ──────────────────────────────────────────────

    def enqueue(self, event: Any, *, copy_event: bool = True) -> None:
        """把事件加入待写缓冲区。

        首条事件触发定时窗口；后续事件在窗口内累积。
        已关闭的缓冲区拒绝入队。

        参数：
        - ``event``：待持久化的事件对象
        - ``copy_event``：是否深拷贝（默认 True，隔离调用方后续修改）
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("WriteBehindBuffer is closed; cannot enqueue")

            if self._apply_backpressure():
                return  # NEWEST 策略：当前事件被丢弃

            self._pending.append(copy.deepcopy(event) if copy_event else event)

            if self._active_write:
                # 写入进行中：入队但不启动新定时器（写入完成后会检查）
                return

            if len(self._pending) == 1 and not self._paused:
                self._arm_timer()

    def flush(self) -> None:
        """显式排空：取消定时器 → 等待当前写入 → 逐批写入直到空。

        阻塞直到所有待写事件落盘或写入失败。
        """
        with self._lock:
            self._cancel_timer()
            self._paused = False
            if not self._pending and not self._active_write:
                return
            # 在锁外执行写入
            pending_snapshot = list(self._pending)
            self._pending.clear()

        self._write_batch(pending_snapshot)

    def dispose(self) -> None:
        """最终排空 + 关闭 sink。幂等。"""
        with self._lock:
            if self._closed:
                return
            self._cancel_timer()
            self._closed = True
            pending_snapshot = list(self._pending)
            self._pending.clear()

        if pending_snapshot:
            self._write_batch(pending_snapshot)
        self._sink.close()

    # ── 内部方法 ──────────────────────────────────────────────

    def _apply_backpressure(self) -> bool:
        """buffer 满时按策略丢弃事件（持锁调用）。

        返回 True 表示当前入队事件应被丢弃（NEWEST 策略）。
        """
        if self._max_buffer_size <= 0:
            return False
        while len(self._pending) >= self._max_buffer_size:
            if self._drop_policy is DropPolicy.NEVER:
                # 不丢弃：无限增长（调用方应通过显式 flush 控制）
                return False
            if self._drop_policy is DropPolicy.OLDEST_FIRST:
                self._pending.pop(0)
                self._dropped_count += 1
            elif self._drop_policy is DropPolicy.NEWEST:
                # 丢弃当前要入队的事件（不入队即可）
                self._dropped_count += 1
                return True
        return False

    def _arm_timer(self) -> None:
        """启动定时窗口（持锁调用）。"""
        self._timer = threading.Timer(self._max_delay_s, self._on_timer_fired)
        self._timer.daemon = True
        self._timer.start()

    def _cancel_timer(self) -> None:
        """取消待触发的定时器（持锁调用）。"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timer_fired(self) -> None:
        """定时器到期：执行一次批量写入。"""
        with self._lock:
            self._timer = None
            if self._active_write or self._paused or not self._pending:
                return
            self._active_write = True
            batch = list(self._pending)
            self._pending.clear()

        try:
            self._sink.append_batch(batch)
        except Exception as exc:
            with self._lock:
                self._pending = batch + self._pending
                self._failure_count += 1
                self._active_write = False
                self._paused = True
            if self._on_failure is not None:
                self._on_failure(exc)
            return
        finally:
            with self._lock:
                self._active_write = False

        # 写入成功后，如果还有新事件，重新启动定时器
        with self._lock:
            if self._pending and not self._paused:
                self._arm_timer()

    def _write_batch(self, batch: list[Any]) -> None:
        """同步批量写入（用于显式 flush / dispose）。"""
        if not batch:
            return
        try:
            self._sink.append_batch(batch)
        except Exception as exc:
            with self._lock:
                self._pending = batch + self._pending
                self._failure_count += 1
            if self._on_failure is not None:
                self._on_failure(exc)
            raise

    def __del__(self) -> None:
        """GC 兜底：确保未显式 dispose 的缓冲关闭定时器。"""
        with contextlib.suppress(Exception):
            self._cancel_timer()


__all__ = [
    "DropPolicy",
    "WriteBehindBuffer",
    "WriteBehindSink",
]
