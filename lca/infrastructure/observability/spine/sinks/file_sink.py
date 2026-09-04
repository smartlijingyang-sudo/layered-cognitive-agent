# COMPAT(delete-when: PR-9, tracking: ADR-0181)
# 旧 EventSpine sink；PR-8 shim 走 events/sinks/spine_* 包装；本模块保留
# 至 PR-9 旧 spine 全退役（rg "lca.plugins.observability.spine.sinks" lca/ = 0 触发）。

"""FileSink — single append-only truth file per run plus per-run exception index.

Append-only JSONL sink writing to ``<run_dir>/<run_id>.spine.jsonl``.
Any ``exception.caught`` event **also** lands in
``<run_dir>/<run_id>.exceptions.jsonl`` so an operator can ``grep
exception_class`` and recover the traceback without consulting the
sidecar map.

Atomic single-line writes: PIPE_BUF (4096 on Linux) guarantees atomic
append. Events ``> 4 KiB`` *or* marked for force-offload
(``exception.caught``) route to a sidecar file and emit a placeholder
in the main ledger.

Sidecar naming is human-readable: ``<sha8>-<safe_class>.json`` —
e.g. ``8a7397b2-CancelledError.json``. The placeholder schema
is uniform: ``{execution_point, offloaded, sidecar}``.

Fsync runs every N events or T ms. Both default to 100, small
enough for crash consistency, large enough that fsync is not on the
hot path.
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
from lca.infrastructure.observability.spine.sinks.naming import (
    DEFAULT_SPINE_TEMPLATE,
    resolve_filename,
    spine_filename_for_run,
)

log = logging.getLogger(__name__)

_ATOMIC_THRESHOLD = 4096  # Linux PIPE_BUF; do NOT change without kernel docs check
_DEFAULT_BATCH = 100
_DEFAULT_INTERVAL_MS = 100

_FORCE_OFFLOAD_EPS: frozenset[str] = frozenset({"exception.caught"})

# ``ValueError`` → ``ValueError``; ``my.module.Error`` → ``my_module_Error``.
_SAFE_CLASS_RE = re.compile(r"[^A-Za-z0-9_]+")


def safe_class_name(exception_class: str) -> str:
    """Sanitize an exception class name into a human-eyeballable token."""
    cleaned = _SAFE_CLASS_RE.sub("_", exception_class).strip("_")
    return cleaned or "Unknown"


def offload_sidecar_path(
    run_dir: Path,
    record: EventRecord,
    encoded: bytes,
    *,
    legacy_sha256_only: bool = False,
) -> tuple[Path, str, str]:
    """Compute sidecar path for an offloaded event.

    Returns ``(path, digest, sidecar_name)``. The default naming is
    ``<sha8>-<safe_class>.json`` (human-readable). Pass
    ``legacy_sha256_only=True`` to get the original ``<sha256>.json``
    layout for older readers.
    """
    digest = hashlib.sha256(encoded).hexdigest()
    if legacy_sha256_only:
        sidecar_name = f"{digest}.json"
    else:
        exc_class = str(record.payload.get("exception_class") or "Unknown")
        sidecar_name = f"{digest[:8]}-{safe_class_name(exc_class)}.json"
    return run_dir / sidecar_name, digest, sidecar_name


def offload_placeholder(*, execution_point: str, offloaded: str, sidecar: str) -> bytes:
    """Build the placeholder line that stands in for an offloaded event.

    Schema is stable — readers grep on ``offloaded``/``sidecar`` keys.
    """
    return (
        json.dumps(
            {"execution_point": execution_point, "offloaded": offloaded, "sidecar": sidecar}
        ).encode("utf-8")
        + b"\n"
    )


def serializable_event(rec: EventRecord) -> dict[str, Any]:
    """Convert ``EventRecord`` → JSON-safe dict (datetime → isoformat)。

    trace_id(ADR-0183 §3.9 PR-12):EventBus.publish 经 ref.trace_id 注入;
    老路径不接 ref 时为 None,序列化输出 ``null``,保持向后兼容。
    """
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
        "trace_id": rec.trace_id,
    }


class FileSink:
    """Append-only JSONL sink with optional per-run exception index.

    Default behaviour:

    - Main ledger: ``<run_dir>/<run_id>.spine.jsonl`` (or ``$run_id.spine.jsonl``
      template via :func:`resolve_filename`).
    - Exception index: ``<run_dir>/<run_id>.exceptions.jsonl``. Every
      ``exception.caught`` event is appended verbatim — grep ``exception_class``
      to triage. Set ``write_exception_index=False`` to disable.

    Backward compatibility:

    - ``spine_filename=True`` is the default; passing it is a no-op.
    - Disable the exception index for legacy test fixtures that don't want
      the extra file.
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        run_id: str,
        file_name: str = DEFAULT_SPINE_TEMPLATE,
        exceptions_file_name: str | None = None,
        write_exception_index: bool = True,
        fsync_batch: int = _DEFAULT_BATCH,
        fsync_interval_ms: int = _DEFAULT_INTERVAL_MS,
        spine_filename: bool = False,
        legacy_sha256_only: bool = False,
    ) -> None:
        self._run_dir = Path(run_dir)
        self._run_id = run_id
        if spine_filename or file_name == DEFAULT_SPINE_TEMPLATE:
            file_name = spine_filename_for_run(run_id)
        else:
            file_name = resolve_filename(file_name, run_id)
        self._path = self._run_dir / file_name
        self._fsync_batch = fsync_batch
        self._fsync_interval_ms = fsync_interval_ms / 1000.0
        self._write_exception_index = write_exception_index
        self._legacy_sha256_only = legacy_sha256_only

        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(
            str(self._path),
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC,
            0o644,
        )

        # Exception index — separate append-only fd so an index glitch
        # never blocks the main ledger path.
        self._exceptions_path: Path | None = None
        self._exceptions_fd: int | None = None
        self._exceptions_count = 0
        if self._write_exception_index:
            exc_name = exceptions_file_name or f"{run_id}.exceptions.jsonl"
            self._exceptions_path = self._run_dir / exc_name
            try:
                self._exceptions_fd = os.open(
                    str(self._exceptions_path),
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC,
                    0o644,
                )
            except OSError as exc:
                log.error(
                    "file_sink: exceptions index open failed run_id=%s err=%s",
                    run_id,
                    exc,
                )
                self._exceptions_fd = None

        self._writes_since_fsync = 0
        self._last_fsync_at = time.monotonic()
        self._closed = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def exceptions_path(self) -> Path | None:
        return self._exceptions_path

    @property
    def exceptions_count(self) -> int:
        return self._exceptions_count

    def write(self, record: EventRecord) -> str | None:
        """Write an event. Returns ``None`` on success, or a short
        ``reason`` token if the **exception index** write failed
        (so the caller — typically :class:`TracingFileSink` — can
        route through its fallback).
        """
        if self._closed:
            raise RuntimeError("FileSink already closed")
        encoded = self._render_encoded(record)
        force_offload = record.execution_point in _FORCE_OFFLOAD_EPS
        if force_offload or len(encoded) > _ATOMIC_THRESHOLD:
            self._offload(record, encoded)
        else:
            os.write(self._fd, encoded)
        self._maybe_fsync(self._fd)
        if force_offload:
            return self._append_exception_index(record)
        return None

    def _render_encoded(self, record: EventRecord) -> bytes:
        line = json.dumps(serializable_event(record), default=str, sort_keys=False)
        return line.encode("utf-8") + b"\n"

    def _offload(self, record: EventRecord, encoded: bytes) -> None:
        sidecar, digest, sidecar_name = offload_sidecar_path(
            self._run_dir, record, encoded, legacy_sha256_only=self._legacy_sha256_only
        )
        sidecar.write_bytes(encoded)
        os.write(
            self._fd,
            offload_placeholder(
                execution_point=record.execution_point,
                offloaded=digest,
                sidecar=sidecar_name,
            ),
        )

    def _append_exception_index(self, record: EventRecord) -> None:
        """Append the full record to the exception index file descriptor.

        Returns the ``reason`` if the write failed (so callers can
        signal up a fallback), or ``None`` on success. Failure modes:
        ``"exceptions_index_failed"`` (write raised) and
        ``"no_exceptions_index"`` (index not configured / already lost).
        """
        if self._exceptions_fd is None:
            return "no_exceptions_index" if not self._write_exception_index else None
        self._exceptions_count += 1
        try:
            line = json.dumps(serializable_event(record), default=str, sort_keys=False)
            os.write(self._exceptions_fd, line.encode("utf-8") + b"\n")
            return None
        except OSError as exc:
            log.error(
                "file_sink: exceptions index write failed run_id=%s err=%s",
                self._run_id,
                exc,
            )
            self._exceptions_fd = None
            return "exceptions_index_failed"

    def _maybe_fsync(self, fd: int) -> None:
        self._writes_since_fsync += 1
        now = time.monotonic()
        if (
            self._writes_since_fsync >= self._fsync_batch
            or (now - self._last_fsync_at) >= self._fsync_interval_ms
        ):
            try:
                os.fsync(fd)
            except OSError as exc:
                log.error("file_sink: fsync failed run_id=%s err=%s", self._run_id, exc)
            self._writes_since_fsync = 0
            self._last_fsync_at = now

    def close(self) -> None:
        if self._closed:
            return
        try:
            os.fsync(self._fd)
            os.close(self._fd)
        except OSError as exc:
            log.error("file_sink: close failed run_id=%s err=%s", self._run_id, exc)
        if self._exceptions_fd is not None:
            try:
                os.fsync(self._exceptions_fd)
                os.close(self._exceptions_fd)
            except OSError as exc:
                log.error(
                    "file_sink: exceptions index close failed run_id=%s err=%s",
                    self._run_id,
                    exc,
                )
            self._exceptions_fd = None
        # P3 slim:0 异常的 run 不留空 ``exceptions.jsonl`` —— close 时若
        # ``exceptions_count == 0``,unlink 占位空文件。 Reader 走
        # ``find_exceptions_file`` / ``journal_exceptions`` 命令已对缺失文件
        # 输出友好提示,语义不变。
        if (
            self._write_exception_index
            and self._exceptions_count == 0
            and self._exceptions_path is not None
        ):
            try:
                self._exceptions_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                log.error(
                    "file_sink: empty exceptions index unlink failed run_id=%s err=%s",
                    self._run_id,
                    exc,
                )
        self._closed = True


__all__ = [
    "FileSink",
    "offload_placeholder",
    "offload_sidecar_path",
    "safe_class_name",
    "serializable_event",
]
