"""Tick 调度器互斥文件锁（ADR-0263 §9①②）。

``ProactiveScheduler`` 与 ``CronScheduler`` 共享的单 flight 文件锁实现：
此前两处是逐字复制的同一仪式（仅锁文件名 / 日志事件名 / unlink 失败
处理三处 drift），现收敛到此单点。

锁文件：``<lock_dir>/<name>.lock``，JSON
``{"owner": "<hostname>:<pid>", "mtime_ms": ...}``；mtime 老于
``min(2 × interval, 90min)`` 视为 stale，收割时记一条
``<name>.lock_stale_reaped`` warning（即收割 trace）。

与 ``lca.application.routine.locks.RoutineFileLock`` 是刻意不同的
seam：后者的契约禁止静默收割（ADR-0263 C2——收割必须返回
``ReclaimTrace``），而 tick 调度器的契约是"收割即记 warning 日志"；
且 import-linter 契约 2 禁止 infrastructure 反向依赖 application。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
from pathlib import Path

_log = logging.getLogger(__name__)

#: ADR-0263 §9②：stale 绝对上限 90 分钟。
STALE_ABSOLUTE_CAP_S = 90 * 60


class SchedulerFileLock:
    """跨 carrier 进程的 tick 调度器互斥文件锁。

    ``name`` 同时决定锁文件名（``<name>.lock``）与收割日志事件名
    （``<name>.lock_stale_reaped``），两个调度器因此永远不会抢同一把锁。
    """

    def __init__(
        self,
        lock_dir: str | Path,
        *,
        name: str,
        default_interval_s: float,
    ) -> None:
        self._lock_dir = Path(lock_dir)
        self._name = name
        self._default_interval_s = default_interval_s

    @property
    def _lock_file(self) -> Path:
        return self._lock_dir / f"{self._name}.lock"

    def acquire(self, now_ms: int) -> bool:
        """取锁：成功 True；被持有 False；stale 则收割后重试一次。"""
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        owner = f"{socket.gethostname()}:{os.getpid()}"
        try:
            with open(self._lock_file, "x", encoding="utf-8") as f:
                json.dump({"owner": owner, "mtime_ms": now_ms}, f)
            return True
        except FileExistsError:
            pass
        try:
            with open(self._lock_file, encoding="utf-8") as f:
                lock = json.load(f)
        except (OSError, ValueError):
            lock = {}
        mtime_ms = int(lock.get("mtime_ms", 0) or 0)
        stale_after_s = min(self._default_interval_s * 2.0, STALE_ABSOLUTE_CAP_S)
        if now_ms - mtime_ms > stale_after_s * 1000:
            _log.warning(
                "%s.lock_stale_reaped owner=%s age_s=%d",
                self._name,
                lock.get("owner"),
                (now_ms - mtime_ms) // 1000,
            )
            try:
                self._lock_file.unlink()
            except OSError:
                # 收割失败（无权限等）：本轮放弃。不能 suppress 后递归重试——
                # unlink 持续失败时那会是无界递归（旧 CronScheduler 拷贝即此
                # drift，现按 ProactiveScheduler 的 fail-closed 语义收敛）。
                return False
            return self.acquire(now_ms)
        return False

    def release(self) -> None:
        with contextlib.suppress(OSError):
            self._lock_file.unlink()


__all__ = [
    "STALE_ABSOLUTE_CAP_S",
    "SchedulerFileLock",
]
