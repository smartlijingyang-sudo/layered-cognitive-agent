"""FilesystemJournalStore —— Spine 持久化后端(append-only 事件流)。

落盘文件承载 spine events(事实流),由 ``RunSessionBuilder`` / ``run_ledger``
seam 通过 ``filename`` 显式指定。``DEFAULT_FILENAME`` 是未指定时的兜底模板。

ADR-0169 PR-27(L10 / D9):默认 ``DEFAULT_FILENAME`` 改为 ``$run_id.spine.jsonl``
模板,通过 ``run_id`` 推导 / 占位符替换得到 ``<run_id>.spine.jsonl``。
``run_id`` 默认 = ``root`` 目录 basename(单 run 实例目录约定)。

PR-4 收口:旧 layout 已退役;新 reader / writer 只能识别 spine 命名。
journal store 的 bootstrap 只看新 spine 路径。

写入路径（write-behind 批量写入,对齐 DSH ``SessionWriteBehind``）:
- ``append`` 先入内存账本（即时可读）,再入 ``WriteBehindBuffer`` 待批量落盘
- ``WriteBehindBuffer`` 按 ``max_delay_ms`` 定时窗口批量写入 ``JsonlFileSink``
- ``JsonlFileSink`` 以追加模式写入,每批一次 ``flush`` + 可选 ``fsync``
- ``flush()`` 强制排空缓冲区;``close()`` 排空并关闭文件句柄
"""

from __future__ import annotations

import json
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
from lca.infrastructure.persistence.jsonl_sink import JsonlFileSink
from lca.infrastructure.persistence.write_behind import WriteBehindBuffer


class FilesystemJournalStore(JournalStoreBackend):
    """Append-only 文件账本（write-behind 批量写入）。"""

    DEFAULT_FILENAME = "$run_id.spine.jsonl"

    def __init__(
        self,
        root: Path | str,
        *,
        run_id: str = "default-run",
        filename: str | None = None,
        fsync_each_append: bool = True,
        max_delay_ms: int = 200,
    ) -> None:
        from lca.infrastructure.observability.spine.sinks.naming import (
            resolve_filename,
        )

        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        # 模板解析:$run_id.spine.jsonl → <run_id>.spine.jsonl
        template = filename if filename is not None else FilesystemJournalStore.DEFAULT_FILENAME
        resolved = resolve_filename(template, run_id)
        # 写入路径总是新 spine 命名(后续 append 落此)
        self._path = self._root / resolved
        self._events: list[StampedEvent] = []

        # bootstrap:仅识别 spine 命名;旧 layout 已下线
        if self._path.exists():
            self._load_existing()

        # write-behind:内存 → 定时批量 → JsonlFileSink 追加落盘
        self._sink = JsonlFileSink(
            self._path,
            fsync=fsync_each_append,
            serializer=self._serialize,
        )
        self._buffer = WriteBehindBuffer(
            self._sink,
            max_delay_ms=max_delay_ms,
        )

    @property
    def path(self) -> Path:
        return self._path

    def _load_existing(self) -> None:
        self._load_existing_at(self._path)

    def _load_existing_at(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
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
        """追加事件:先入内存账本（即时可读），再入 write-behind 待批量落盘。"""
        # 1. 内存记账(允许并发读 snapshot)
        self._events.append(stamped)
        # 2. 入 write-behind buffer（定时批量落盘）
        self._buffer.enqueue(stamped)
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
        """强制排空缓冲区,确保所有待写事件落盘。"""
        self._buffer.flush()

    def close(self) -> None:
        """排空缓冲区并关闭文件句柄;幂等。"""
        self._buffer.dispose()

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
