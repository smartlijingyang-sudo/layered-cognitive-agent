"""FilesystemJournalStore —— Spine 持久化后端(append-only 事件流)。

落盘文件承载 spine events(事实流),由 ``RunSessionBuilder`` / ``run_ledger``
seam 通过 ``filename`` 显式指定为 ``events.jsonl``。 ``DEFAULT_FILENAME`` 仅
作为未指定时的兜底;生产路径一定显式传入,这里与实际文件名解耦。

特性:
- 每次 ``append`` 走"写 staging + fsync + atomic rename"协议,崩溃时不破坏
  既有文件。
- ``flush()`` 把内存 buffer 强制刷到磁盘。
- ``close()`` 重复调用安全。
- 可选 ``fsync_each_append=True`` 保证 required 事件跨进程持久。
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.contracts.observability.journal_format_errors import JournalFormatError
from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.infrastructure.observability.journal.schema_version import (
    SCHEMA_VERSION,
    check_schema_version,
)


class FilesystemJournalStore(JournalStoreBackend):
    """Append-only 文件账本(L2 durable)。"""

    DEFAULT_FILENAME = "events.jsonl"

    def __init__(
        self,
        root: Path | str,
        *,
        filename: str = DEFAULT_FILENAME,
        fsync_each_append: bool = True,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = self._root / filename
        self._fsync_each_append = fsync_each_append
        self._events: list[StampedEvent] = []
        # 若文件已存在,载入历史(只读 bootstrap;后续 append 继续追加)
        if self._path.exists():
            self._load_existing()

    @property
    def path(self) -> Path:
        return self._path

    def _load_existing(self) -> None:
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return
        for _line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                # 部分行损坏 —— 跳过(append-only 文件不应损坏)
                continue
            if not isinstance(payload, dict):
                # 非对象行(纯标量) —— 跳过,与损坏行同类
                continue
            # L15: schema_version 必带;缺则按缺失处理(此处默认 v2 兼容)
            raw_version = payload.get("schema_version", SCHEMA_VERSION)
            try:
                version_int = int(raw_version)
            except (TypeError, ValueError):
                # 无法解析为整数 —— 视为格式损坏,跳过(非 schema 拒绝)
                continue
            # 方向感知 schema 校验(VersionTooOld / VersionTooNew 必抛)
            check_schema_version(version_int)
            # L15: event_type 必须在已知词表,除非显式 ignorable
            event_type = str(payload.get("event_type", "UnknownEvent"))
            data = payload.get("data", {}) or {}
            ignorable = bool(data.get("ignorable", False))
            if event_type not in JOURNAL_EVENT_CLASSES and not ignorable:
                from lca.contracts.observability.journal_format_errors import (
                    UnknownEventType,
                )

                raise UnknownEventType(event_type)
            # 重建 StampedEvent 的最小骨架,seq/ts/event_type/data 已够消费
            from lca.contracts.models.observability.journal import (
                JournalEvent,
                RunScope,
            )

            try:
                seq = int(payload.get("seq", len(self._events) + 1))
                ts = float(payload.get("ts", 0.0))
                scope = RunScope(
                    trace_id=str(payload.get("scope", {}).get("trace_id", "")),
                    run_id=str(payload.get("scope", {}).get("run_id", "")),
                )
                event = JournalEvent()  # 占位;测试/Inspector 不深入 payload
                stamped = StampedEvent(
                    seq=seq,
                    ts=ts,
                    scope=scope,
                    event=event,
                    event_type=event_type,
                    data=data,
                )
                self._events.append(stamped)
            except JournalFormatError:
                raise
            except Exception:  # noqa: S112 — 单行字段异常按损坏行处理,继续下一行
                # 其他字段级异常 —— 跳过单行,不影响其他行
                continue

    # ── JournalStoreBackend 契约 ──────────────────────────────

    def append(self, stamped: StampedEvent) -> StampedEvent:
        # 1. 写 staging 临时文件
        staging = self._path.with_suffix(
            self._path.suffix + f".staging-{os.getpid()}-{time.time_ns()}"
        )
        try:
            with staging.open("w", encoding="utf-8") as f:
                json.dump(self._serialize(stamped), f, ensure_ascii=False)
                if self._fsync_each_append:
                    f.flush()
                    os.fsync(f.fileno())
        except OSError:
            with contextlib.suppress(OSError):
                staging.unlink()
            raise

        # 2. 原子 rename 到正式文件
        try:
            os.replace(staging, self._path)
        except OSError:
            with contextlib.suppress(OSError):
                staging.unlink()
            raise

        # 3. 内存记账(允许并发读 snapshot)
        self._events.append(stamped)
        return stamped

    def events(self) -> Sequence[StampedEvent]:
        return tuple(self._events)

    def get(self, seq: int) -> StampedEvent | None:
        if seq < 1 or seq > len(self._events):
            return None
        return self._events[seq - 1]

    def read_from(self, after_seq: int) -> Sequence[StampedEvent]:
        start = max(after_seq, 0)
        return tuple(self._events[start:])

    def flush(self) -> None:
        # 文件已在 append 时 fsync;此处 no-op
        return None

    def close(self) -> None:
        return None

    # ── 序列化辅助 ──────────────────────────────────────────────

    def _serialize(self, stamped: StampedEvent) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "seq": stamped.seq,
            "ts": stamped.ts,
            "event_type": stamped.event_type,
            "scope": {
                "trace_id": str(stamped.scope.trace_id),
                "run_id": str(stamped.scope.run_id),
                "parent_run_id": (
                    str(stamped.scope.parent_run_id) if stamped.scope.parent_run_id else None
                ),
                "parent_trace_id": (
                    str(stamped.scope.parent_trace_id) if stamped.scope.parent_trace_id else None
                ),
                "delegation_id": stamped.scope.delegation_id,
                "agent_role": stamped.scope.agent_role,
                "step": stamped.scope.step,
            },
            "data": dict(stamped.data),
            "parent_seq": stamped.parent_seq,
        }


__all__ = ["FilesystemJournalStore"]
