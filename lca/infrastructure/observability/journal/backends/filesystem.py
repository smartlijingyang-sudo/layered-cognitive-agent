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
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal.catalog import JOURNAL_EVENT_CLASSES
from lca.contracts.models.observability.journal.journal import StampedEvent
from lca.contracts.observability.journal.format_errors import JournalFormatError
from lca.contracts.observability.journal.store import JournalStoreBackend
from lca.infrastructure.observability.journal.schema_version import (
    SCHEMA_VERSION,
    check_schema_version,
)
from lca.infrastructure.observability.spine.sinks.naming import (
    DEFAULT_SPINE_TEMPLATE,
    resolve_filename,
)
from lca.infrastructure.persistence.jsonl_sink import JsonlFileSink
from lca.infrastructure.persistence.write_behind import WriteBehindBuffer

log = logging.getLogger(__name__)


class FilesystemJournalStore(JournalStoreBackend):
    """Append-only 文件账本（write-behind 批量写入）。"""

    DEFAULT_FILENAME = DEFAULT_SPINE_TEMPLATE

    def __init__(
        self,
        root: Path | str,
        *,
        run_id: str = "default-run",
        filename: str | None = None,
        fsync_each_append: bool = True,
        max_delay_ms: int = 200,
    ) -> None:
        from lca.infrastructure.persistence.run_paths import ensure_run_dir

        self._root = Path(root)
        ensure_run_dir(self._root)
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
            raw = path.read_bytes()
        except OSError as exc:
            raise JournalFormatError(f"{path}: failed to read journal: {exc}") from exc

        lines = raw.splitlines(keepends=True)
        offset = 0
        for line_no, raw_line in enumerate(lines, start=1):
            line_offset = offset
            offset += len(raw_line)
            is_last = line_no == len(lines)
            terminated = raw_line.endswith(b"\n")
            content = raw_line[:-1] if terminated else raw_line
            if content.endswith(b"\r"):
                content = content[:-1]
            try:
                text = content.decode("utf-8")
                payload = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                if is_last and not terminated and self._is_confirmed_incomplete_tail(content, exc):
                    self._truncate_partial_tail(path, line_offset, line_no, exc)
                    return
                reason = "invalid UTF-8" if isinstance(exc, UnicodeDecodeError) else "invalid JSON"
                raise JournalFormatError(f"{path}: line {line_no}: {reason}: {exc}") from exc
            if not isinstance(payload, dict):
                raise JournalFormatError(
                    f"{path}: line {line_no}: expected a JSON object, got {type(payload).__name__}"
                )
            if not text.strip():
                raise JournalFormatError(f"{path}: line {line_no}: empty journal record")

            # L15: schema_version 必带;缺则按缺失处理(此处默认 v2 兼容)
            raw_version = payload.get("schema_version", SCHEMA_VERSION)
            try:
                version_int = int(raw_version)
            except (TypeError, ValueError) as exc:
                raise JournalFormatError(
                    f"{path}: line {line_no}: invalid schema_version {raw_version!r}"
                ) from exc
            # 方向感知 schema 校验(VersionTooOldError / VersionTooNewError 必抛)
            check_schema_version(version_int)
            # L15: event_type 必须在已知词表,除非显式 ignorable
            event_type = str(payload.get("event_type", "UnknownEvent"))
            data = payload.get("data", {})
            if not isinstance(data, dict):
                raise JournalFormatError(f"{path}: line {line_no}: expected data to be an object")
            ignorable = bool(data.get("ignorable", False))
            if event_type not in JOURNAL_EVENT_CLASSES and not ignorable:
                from lca.contracts.observability.journal.format_errors import (
                    UnknownEventTypeError,
                )

                raise UnknownEventTypeError(event_type)
            # 重建 StampedEvent 的最小骨架,seq/ts/event_type/data 已够消费
            from lca.contracts.atoms.ids.ids import RunId, TraceId
            from lca.contracts.models.observability.journal.journal import (
                JournalEvent,
                RunScope,
            )

            try:
                expected_seq = len(self._events) + 1
                seq = int(payload.get("seq", expected_seq))
                if seq != expected_seq:
                    raise JournalFormatError(
                        f"{path}: line {line_no}: expected seq={expected_seq}, got seq={seq}"
                    )
                ts = float(payload.get("ts", 0.0))
                scope_data = payload.get("scope", {})
                if not isinstance(scope_data, dict):
                    raise JournalFormatError(
                        f"{path}: line {line_no}: failed to reconstruct journal event: "
                        "expected scope to be an object"
                    )
                scope = RunScope(
                    trace_id=TraceId(str(scope_data.get("trace_id", ""))),
                    run_id=RunId(str(scope_data.get("run_id", ""))),
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
            except JournalFormatError:
                raise
            except Exception as exc:
                raise JournalFormatError(
                    f"{path}: line {line_no}: failed to reconstruct journal event: {exc}"
                ) from exc

            if is_last and not terminated:
                self._terminate_valid_tail(path, offset, line_no)
            self._events.append(stamped)

    @staticmethod
    def _is_confirmed_incomplete_tail(content: bytes, error: Exception) -> bool:
        """Recognize only an EOF-truncated JSON token or UTF-8 code point."""
        if not content.strip():
            return False
        if isinstance(error, UnicodeDecodeError):
            return error.reason == "unexpected end of data" and error.end == len(content)
        if isinstance(error, json.JSONDecodeError):
            return error.pos >= len(error.doc) or error.msg.startswith("Unterminated string")
        return False

    @staticmethod
    def _truncate_partial_tail(path: Path, offset: int, line_no: int, cause: Exception) -> None:
        """Discard only a malformed, unterminated final record after a crash."""
        try:
            with path.open("r+b") as stream:
                stream.truncate(offset)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise JournalFormatError(
                f"{path}: line {line_no}: could not repair trailing partial record: {exc}"
            ) from exc
        log.warning(
            "repaired trailing partial journal record path=%s line=%d reason=%s",
            path,
            line_no,
            cause,
        )

    @staticmethod
    def _terminate_valid_tail(path: Path, offset: int, line_no: int) -> None:
        """Add the JSONL delimiter to a valid final record before future appends."""
        try:
            with path.open("ab") as stream:
                stream.write(b"\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise JournalFormatError(
                f"{path}: line {line_no}: could not terminate valid journal record: {exc}"
            ) from exc
        log.warning(
            "completed missing trailing journal delimiter path=%s line=%d offset=%d",
            path,
            line_no,
            offset,
        )

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
