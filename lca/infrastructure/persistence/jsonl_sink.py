"""JSONL 文件批量写入后端 —— ``WriteBehindSink`` 的文件系统实现。

ADR-0186: Session persistence 内部基础设施。由 ``FilesystemJournalStore``
通过 ``WriteBehindBuffer`` 消费，不接受新的直接调用方。

对齐 DSH ``PersistenceBackend.appendBatch`` 的语义：

- 长驻文件句柄（不逐条开关）
- 每批一次 ``flush`` + 可选 ``fsync``
- 追加模式（不覆盖已有内容）
- ``close()`` 幂等

崩溃恢复：调用方在读取时校验事件序列连续性；
尾部截断的行视为"撕裂尾"，由读取端跳过。
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from lca.infrastructure.persistence.write_behind import WriteBehindSink


class JsonlFileSink(WriteBehindSink):
    """把事件批量追加写入一个 JSONL 文件。

    每行一个事件，``json.dumps`` 序列化。

    参数：
    - ``path``：目标文件路径（父目录不存在时自动创建）
    - ``fsync``：每批写入后是否 ``os.fsync``（生产 True，测试 False）
    - ``serializer``：事件 → JSON 可序列化 dict 的函数；
      缺省用 ``dataclasses.asdict``，兜底 ``dict()``
    """

    def __init__(
        self,
        path: Path | str,
        *,
        fsync: bool = True,
        serializer: Callable[[Any], dict[str, Any]] | None = None,
    ) -> None:
        self._path = Path(path)
        self._fsync = fsync
        self._serializer = serializer or _default_serializer
        self._handle: Any = None
        self._closed = False

    @property
    def path(self) -> Path:
        return self._path

    def append_batch(self, events: Sequence[Any]) -> None:
        """把一批事件追加写入文件，单次 flush + 可选 fsync。"""
        if self._closed:
            raise RuntimeError(f"JsonlFileSink is closed: {self._path}")
        if not events:
            return

        handle = self._ensure_open()
        lines: list[str] = []
        for event in events:
            payload = self._serializer(event)
            lines.append(json.dumps(payload, ensure_ascii=False, default=str))

        handle.write("\n".join(lines) + "\n")
        handle.flush()
        if self._fsync:
            os.fsync(handle.fileno())

    def close(self) -> None:
        """关闭文件句柄；幂等。"""
        if self._closed:
            return
        self._closed = True
        if self._handle is not None:
            with contextlib.suppress(OSError):
                self._handle.flush()
            with contextlib.suppress(OSError):
                self._handle.close()
            self._handle = None

    def _ensure_open(self) -> Any:
        """确保文件句柄已打开（追加模式）。"""
        if self._handle is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self._path.open("a", encoding="utf-8")
        return self._handle


def _default_serializer(event: Any) -> dict[str, Any]:
    """默认序列化：优先 dataclasses.asdict，兜底 dict()。"""
    try:
        import dataclasses

        if dataclasses.is_dataclass(event) and not isinstance(event, type):
            return dataclasses.asdict(event)
    except (TypeError, ValueError):
        pass
    if isinstance(event, dict):
        return event
    if hasattr(event, "to_dict"):
        return event.to_dict()
    return dict(event)


__all__ = ["JsonlFileSink"]
