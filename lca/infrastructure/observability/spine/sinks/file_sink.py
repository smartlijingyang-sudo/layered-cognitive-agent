"""FileSink — single append-only truth file per run.

Atomic single-line writes via O_APPEND + size ≤ PIPE_BUF (4096 bytes
on Linux guarantees atomic append). Events > 4 KB are offloaded to
``<event_hash>.json`` sidecars (I10).

Fsync runs on a counter (every N events) and timer (every T ms). Both
default to ``100`` — small enough for crash consistency, large enough
that fsync is not on the hot path.

ADR-0169 PR-27:默认文件名 = ``$run_id.spine.jsonl`` 模板,实例化时通过
:func:`resolve_filename` 替换为 ``<run_id>.spine.jsonl``(L10 / D9)。
旧字面 ``events.jsonl`` 仍可显式传入,获得向后兼容的旧布局。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.naming import (
    DEFAULT_SPINE_TEMPLATE,
    resolve_filename,
    spine_filename_for_run,
)

_ATOMIC_THRESHOLD = 4096  # Linux PIPE_BUF; do NOT change without kernel docs check
_DEFAULT_BATCH = 100
_DEFAULT_INTERVAL_MS = 100


class FileSink:
    """Append-only JSONL sink 默认落盘 ``<run_dir>/<run_id>.spine.jsonl``。

    ADR-0169 L10:
    - 默认 ``file_name`` 模板 = ``$run_id.spine.jsonl`` → 实例化为
      ``<run_id>.spine.jsonl``(PR-27)。
    - ``spine_filename=True`` 时同样解析为 ``<run_id>.spine.jsonl``;
      默认值已等价于 ``spine_filename=True``,保留该参数仅为兼容既有调用方。
    - 显式 ``file_name="events.jsonl"`` 仍生效,获得旧布局(向后兼容)。
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        run_id: str,
        file_name: str = DEFAULT_SPINE_TEMPLATE,
        fsync_batch: int = _DEFAULT_BATCH,
        fsync_interval_ms: int = _DEFAULT_INTERVAL_MS,
        spine_filename: bool = False,
    ) -> None:
        self._run_dir = Path(run_dir)
        self._run_id = run_id
        # 解析 $run_id 占位符 → 实际 per-run 文件名
        if spine_filename or file_name == DEFAULT_SPINE_TEMPLATE:
            file_name = spine_filename_for_run(run_id)
        else:
            file_name = resolve_filename(file_name, run_id)
        self._path = self._run_dir / file_name
        self._fsync_batch = fsync_batch
        self._fsync_interval_ms = fsync_interval_ms / 1000.0

        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(
            str(self._path),
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_CLOEXEC,
            0o644,
        )
        self._writes_since_fsync = 0
        self._last_fsync_at = time.monotonic()
        self._closed = False

    @property
    def path(self) -> Path:
        return self._path

    def write(self, record: EventRecord) -> None:
        if self._closed:
            raise RuntimeError("FileSink already closed")
        line = json.dumps(_serializable(record), default=str, sort_keys=False)
        encoded = line.encode("utf-8") + b"\n"
        if len(encoded) <= _ATOMIC_THRESHOLD:
            os.write(self._fd, encoded)
        else:
            digest = hashlib.sha256(encoded).hexdigest()
            sidecar = self._run_dir / f"{digest}.json"
            sidecar.write_bytes(encoded)
            placeholder = json.dumps(
                {
                    "execution_point": record.execution_point,
                    "offloaded": digest,
                }
            )
            os.write(self._fd, placeholder.encode("utf-8") + b"\n")

        self._writes_since_fsync += 1
        now = time.monotonic()
        if (
            self._writes_since_fsync >= self._fsync_batch
            or (now - self._last_fsync_at) >= self._fsync_interval_ms
        ):
            os.fsync(self._fd)
            self._writes_since_fsync = 0
            self._last_fsync_at = now

    def close(self) -> None:
        if self._closed:
            return
        os.fsync(self._fd)
        os.close(self._fd)
        self._closed = True


def _serializable(rec: EventRecord) -> dict[str, Any]:
    """Convert EventRecord → JSON-safe dict (datetime → isoformat)."""
    d = {
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
    return d
