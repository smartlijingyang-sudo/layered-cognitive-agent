"""SpineSink —— 事实链 SSOT 默认实现 —— ADR-0183 §3.5 + I-FW-SSOT-1。

唯一写入 <run_id>.spine.jsonl。plugin 不可改 to_dict() 字节布局。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from lca_kernel.events.sinks import SinkBackend

if TYPE_CHECKING:
    from lca_kernel.events.spine_runtime import SpineEventRecord

log = logging.getLogger(__name__)


class SpineSinkClosedError(RuntimeError):
    """SpineSink.append 在 fd 已关闭时调用。"""

    def __init__(self, path: Path) -> None:
        super().__init__(f"SpineSink({path}) 已关闭，不可 append")
        self.path = path


class SpineSink(SinkBackend):
    """事实链 SSOT 落盘实现（I-FW-SSOT-1）。

    fsync 策略：
    - ``batch``（默认）：每 ``fsync_batch_size`` 条或 ``fsync_interval_ms`` 毫秒触发一次 fsync
    - 任何 fsync 失败 → raise（PR-4 不实装重试，留 follow-up）
    """

    def __init__(
        self,
        path_template: str = "{run_id}.spine.jsonl",
        *,
        fsync_strategy: str = "batch",
        fsync_batch_size: int = 100,
        fsync_interval_ms: int = 50,
        checksum_on_open: bool = True,
    ) -> None:
        self._path_template = path_template
        self._fsync_strategy = fsync_strategy
        self._fsync_batch_size = fsync_batch_size
        self._fsync_interval_ms = fsync_interval_ms
        self._checksum_on_open = checksum_on_open
        # 内部状态：fd 句柄 + fsync 节奏计数器
        self._path: Path | None = None
        self._fd: IO[str] | None = None
        self._buffer_count: int = 0
        self._last_fsync: float = 0.0
        # run_id 在 open() 时由调用方提供
        self._run_id: str | None = None

    # ── 生命周期 ────────────────────────────────────────────────────────

    def set_run_id(self, run_id: str) -> None:
        """绑定 run_id + 打开底层 fd。

        append/flush/close 必须先调本方法。run_id 替换 ``path_template`` 中的
        ``{run_id}`` 段。打开失败 raise（让 caller 决定怎么处理）。
        """
        if self._fd is not None:
            raise RuntimeError("SpineSink 已 open；不可重复 set_run_id")
        self._run_id = run_id
        self._path = Path(self._path_template.replace("{run_id}", run_id))
        # open 时机：append 之前必须先 open（I-FW-SSOT-1 的 fsync 节奏依赖 fd）
        self._fd = self._path.open("a", encoding="utf-8")
        self._buffer_count = 0
        self._last_fsync = time.monotonic()
        log.debug(
            "SpineSink.open",
            extra={"run_id": run_id, "path": str(self._path)},
        )

    def append(self, record: SpineEventRecord) -> None:
        """落盘一条 record。"""
        if self._fd is None or self._path is None:
            raise SpineSinkClosedError(self._path or Path("<unbound>"))
        line: dict[str, Any] = record.to_dict()
        self._fd.write(json.dumps(line, sort_keys=True) + "\n")
        self._buffer_count += 1
        self._maybe_fsync()

    def flush(self) -> None:
        """显式 fsync。"""
        if self._fd is None or self._path is None:
            raise SpineSinkClosedError(self._path or Path("<unbound>"))
        self._fd.flush()
        import os

        os.fsync(self._fd.fileno())
        self._buffer_count = 0
        self._last_fsync = time.monotonic()

    def close(self) -> None:
        """flush + close。close 后再 append/flush 会 raise。"""
        if self._fd is None:
            return
        try:
            self.flush()
        finally:
            self._fd.close()
            self._fd = None

    # ── 内部 ────────────────────────────────────────────────────────────

    def _maybe_fsync(self) -> None:
        """按策略触发 fsync（batch：条数 or 时间阈值）。"""
        if self._fsync_strategy != "batch":
            return
        if self._fd is None or self._path is None:
            return
        elapsed_ms = (time.monotonic() - self._last_fsync) * 1000.0
        if self._buffer_count >= self._fsync_batch_size or elapsed_ms >= self._fsync_interval_ms:
            self.flush()


__all__ = ["SpineSink", "SpineSinkClosedError"]
