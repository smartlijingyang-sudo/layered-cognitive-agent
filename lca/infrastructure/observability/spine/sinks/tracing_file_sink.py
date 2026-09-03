"""TracingFileSink — 保证 traceback 必落盘的 FileSink 包装。

承接 K6 fail-loud SSOT(ADR-2026-09-03):从 webserver 入口到后端任何
异常都必须落盘,**写不进去不能让进程崩**。这是观测层最严的不变量。

设计:三道防线 + 绝不抛
====================

1. **主 ledger** (``<run_id>.spine.jsonl``):FileSink 行为不变,O_APPEND +
   4 KiB atomic + 大 payload offload 到 sidecar。失败 → 第二道。
2. **异常专用索引** (``<run_id>.exceptions.jsonl``):任何 ``exception.caught``
   EP 额外追加到这里,与主 ledger 并列。一行一个完整 JSON event,grep
   ``exception_class`` 一刀命中。失败 → 第三道。
3. **本地 fallback** (``<run_id>.FALLBACK.log``):任何上面 IOError 都退化到
   这里,只写一行 JSON + ``fallback_reason`` 字段。失败 → 第四道。
4. **structlog ERROR** (进程级最后兜底):文件系统彻底不可用时,只走
   structlog,留 ``trace_id`` + ``run_id`` + ``exception_class`` 给人查。

不抛保证
--------
``write()`` 内部任何异常都被 swallow(structlog ERROR 记录),绝不把
OSError 抛到 caller —— 因为 caller 是 spine append 的热路径,抛了会让
上游整个 request 失败,反过来又触发新的异常,递归风暴。

Sidecar 文件名可读
----------------
offload 出来的 sidecar 名是 ``<sha256[:8]>-<safe_class>.json``
(默认行为),纯 sha256 保留为 ``legacy_sha256_only=True`` 可选。
人眼 ``ls`` 一眼能看出哪类异常,grep 不再依赖 payload hash。

manifest 顶层 ``exceptions_count``
----------------------------------
``exceptions_count`` 是 property,实时反映本 sink 写过的
exception.caught 事件数。manifest flush 时读取这个数字写到顶层
(SSOT),不需要 grep 主 ledger。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
from lca.infrastructure.observability.spine.sinks.naming import (
    DEFAULT_SPINE_TEMPLATE,
    resolve_filename,
    spine_filename_for_run,
)

log = logging.getLogger(__name__)

_ATOMIC_THRESHOLD = 4096
_DEFAULT_BATCH = 100
_DEFAULT_INTERVAL_MS = 100

_FORCE_OFFLOAD_EPS: frozenset[str] = frozenset({"exception.caught"})

# exception_class 安全文件名片段(剔除非字母数字)
_SAFE_CLASS_RE = re.compile(r"[^A-Za-z0-9_]+")


def _safe_class_name(exception_class: str) -> str:
    """``AttributeError`` / ``ValueError`` → ``AttributeError``(自身已合规)。

    未知第三方类 ``my.module.Error`` → ``my_module_Error``。
    """
    cleaned = _SAFE_CLASS_RE.sub("_", exception_class).strip("_")
    return cleaned or "Unknown"


class TracingFileSink:
    """保证 traceback 必落盘的 FileSink 包装。

    接口与 FileSink 兼容 (path / write / close),多出:
    - ``exceptions_path`` 属性:异常专用索引路径
    - ``exceptions_count`` 属性:实时异常计数
    - 任何 IOError 都不抛,自动 fallback 到 FALLBACK.log / structlog

    构造参数:
    - run_dir, run_id: 同 FileSink
    - file_name: 同 FileSink
    - exceptions_file_name: 异常索引文件名,默认 ``<run_id>.exceptions.jsonl``
    - legacy_sha256_only: True 时 sidecar 名仍是纯 sha256 (向后兼容老 reader)
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        run_id: str,
        file_name: str = DEFAULT_SPINE_TEMPLATE,
        exceptions_file_name: str | None = None,
        fsync_batch: int = _DEFAULT_BATCH,
        fsync_interval_ms: int = _DEFAULT_INTERVAL_MS,
        spine_filename: bool = False,
        legacy_sha256_only: bool = False,
    ) -> None:
        self._run_dir = Path(run_dir)
        self._run_id = run_id
        # 解析文件名模板 → 实际 per-run 文件名(同 FileSink)
        if spine_filename or file_name == DEFAULT_SPINE_TEMPLATE:
            file_name = spine_filename_for_run(run_id)
        else:
            file_name = resolve_filename(file_name, run_id)
        self._file_name = file_name
        self._legacy_sha256_only = legacy_sha256_only
        self._fsync_batch = fsync_batch
        self._fsync_interval_ms = fsync_interval_ms / 1000.0

        # 内部 FileSink,失败被 swallow 后我们再走自己的 fallback
        self._main = FileSink(
            self._run_dir,
            run_id=run_id,
            file_name=file_name,
            fsync_batch=fsync_batch,
            fsync_interval_ms=fsync_interval_ms,
            spine_filename=spine_filename,
        )

        # 异常专用索引文件句柄(可选)
        self._exceptions_path: Path | None = None
        self._exceptions_fd: int | None = None
        self._exceptions_count = 0
        exc_name = exceptions_file_name or f"{run_id}.exceptions.jsonl"
        self._exceptions_path = self._run_dir / exc_name
        try:
            self._run_dir.mkdir(parents=True, exist_ok=True)
            self._exceptions_fd = os.open(
                str(self._exceptions_path),
                os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC,
                0o644,
            )
        except OSError as exc:
            # 第二道防线初始化失败 → 不致命,后续 write 仍会尝试 fallback
            log.error(
                "tracing_sink: exceptions index open failed run_id=%s err=%s",
                run_id, exc,
            )
            self._exceptions_fd = None

        # Fallback 文件路径(任何 IOError 都追加到这里)
        self._fallback_path = self._run_dir / "FALLBACK.log"
        self._writes_since_fsync = 0
        self._last_fsync_at = time.monotonic()
        self._closed = False

    # ── Public surface ──────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._main.path

    @property
    def exceptions_path(self) -> Path | None:
        return self._exceptions_path

    @property
    def exceptions_count(self) -> int:
        return self._exceptions_count

    def write(self, record: EventRecord) -> None:
        """写一个 event。绝不抛。

        路径:try main → OSError → fallback
        如果是 exception.caught EP,额外追加到 exceptions.jsonl(同样
        三道防线)。
        """
        if self._closed:
            # 已关闭:不抛(防止 caller 被打断),只走 fallback
            self._write_fallback(record, reason="sink_closed")
            return
        try:
            self._write_with_offload(record)
        except Exception as exc:
            # 第二道防线:主 ledger 失败
            self._write_fallback(record, reason=f"main_failed:{exc!r}")
        finally:
            # 如果是异常 EP,额外索引(同样三道防线)
            if record.execution_point in _FORCE_OFFLOAD_EPS:
                self._write_exception_index(record)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._main.close()
        except Exception as exc:
            log.error("tracing_sink: main.close failed run_id=%s err=%s",
                      self._run_id, exc)
        if self._exceptions_fd is not None:
            try:
                os.fsync(self._exceptions_fd)
                os.close(self._exceptions_fd)
            except Exception as exc:
                log.error(
                    "tracing_sink: exceptions index close failed run_id=%s err=%s",
                    self._run_id, exc,
                )
            self._exceptions_fd = None

    # ── Internals ───────────────────────────────────────────────────

    def _write_with_offload(self, record: EventRecord) -> None:
        """主 ledger 写入,>4 KiB offload 到 sidecar(可读名)。"""
        line = json.dumps(_serializable(record), default=str, sort_keys=False)
        encoded = line.encode("utf-8") + b"\n"
        force_offload = record.execution_point in _FORCE_OFFLOAD_EPS
        if len(encoded) <= _ATOMIC_THRESHOLD and not force_offload:
            os.write(self._main._fd, encoded)  # type: ignore[attr-defined]
        else:
            self._offload_sidecar(record, encoded)
        # Fsync 调度
        self._writes_since_fsync += 1
        now = time.monotonic()
        if (
            self._writes_since_fsync >= self._fsync_batch
            or (now - self._last_fsync_at) >= self._fsync_interval_ms
        ):
            try:
                os.fsync(self._main._fd)  # type: ignore[attr-defined]
            except OSError as exc:
                log.error("tracing_sink: main fsync failed run_id=%s err=%s",
                          self._run_id, exc)
            self._writes_since_fsync = 0
            self._last_fsync_at = now

    def _offload_sidecar(self, record: EventRecord, encoded: bytes) -> None:
        """Offload 到 sidecar。可读名 ``<sha8>-<SafeClass>.json``。"""
        digest = hashlib.sha256(encoded).hexdigest()
        if self._legacy_sha256_only:
            sidecar_name = f"{digest}.json"
        else:
            exc_class = str(record.payload.get("exception_class") or "Unknown")
            safe = _safe_class_name(exc_class)
            sidecar_name = f"{digest[:8]}-{safe}.json"
        sidecar = self._run_dir / sidecar_name
        sidecar.write_bytes(encoded)
        placeholder = json.dumps(
            {
                "execution_point": record.execution_point,
                "offloaded": digest,
                "sidecar": sidecar_name,
            },
            default=str,
        )
        os.write(self._main._fd, placeholder.encode("utf-8") + b"\n")  # type: ignore[attr-defined]

    def _write_exception_index(self, record: EventRecord) -> None:
        """追加到 <run_id>.exceptions.jsonl。三道防线。"""
        self._exceptions_count += 1
        try:
            line = json.dumps(_serializable(record), default=str, sort_keys=False)
            encoded = line.encode("utf-8") + b"\n"
            if self._exceptions_fd is not None:
                os.write(self._exceptions_fd, encoded)
                return
        except Exception as exc:
            log.error("tracing_sink: exceptions index write failed run_id=%s err=%s",
                      self._run_id, exc)
            self._exceptions_fd = None  # 后续不再尝试,直接 fallback
        # Fallback
        self._write_fallback(record, reason="exceptions_index_failed")

    def _write_fallback(self, record: EventRecord, *, reason: str) -> None:
        """第四道防线:任何上面失败都写到 FALLBACK.log。

        FALLBACK.log 也失败 → structlog ERROR(进程级最后兜底)。
        """
        try:
            line = json.dumps(
                {
                    "fallback_reason": reason,
                    "execution_point": record.execution_point,
                    "run_id": record.run_id,
                    "when": record.when.isoformat() if record.when else None,
                    "payload_summary": _summarize_payload(record.payload),
                },
                default=str,
            )
            with self._fallback_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as exc:
            # structlog 兜底:文件系统彻底不可用
            log.error(
                "tracing_sink: FALLBACK write FAILED run_id=%s ep=%s reason=%s err=%s",
                self._run_id, record.execution_point, reason, exc,
                extra={
                    "run_id": self._run_id,
                    "execution_point": record.execution_point,
                    "fallback_reason": reason,
                    "exception_class": str(record.payload.get("exception_class", "?")),
                },
            )


def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Fallback 行只保留 payload 摘要,避免 traceback 全文重复落 4 道。"""
    if not isinstance(payload, dict):
        return {"_type": type(payload).__name__}
    return {
        "exception_class": payload.get("exception_class"),
        "exception_message": payload.get("exception_message"),
        "boundary": payload.get("boundary"),
        "source_location": payload.get("source_location"),
    }


def _serializable(rec: EventRecord) -> dict[str, Any]:
    """EventRecord → JSON-safe dict(同 FileSink)。"""
    return {
        "execution_point": rec.execution_point,
        "channel": rec.channel,
        "span_id": rec.span_id,
        "parent_span_id": rec.parent_span_id,
        "sequence": rec.sequence,
        "epoch": rec.epoch,
        "causality_id": rec.causality_id,
        "outcome": rec.outcome,
        "when": rec.when.isoformat(),
        "when_corrected": rec.when_corrected.isoformat(),
        "prev_event_hash": rec.prev_event_hash,
        "run_id": rec.run_id,
        "step_id": rec.step_id,
        "payload": rec.payload,
        "phase": rec.phase,
        "reason": rec.reason,
    }


__all__ = [
    "_FORCE_OFFLOAD_EPS",
    "TracingFileSink",
    "_safe_class_name",
]
