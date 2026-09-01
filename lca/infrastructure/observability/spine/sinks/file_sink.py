"""FileSink — single append-only truth file per run.

Atomic single-line writes via O_APPEND + size ≤ PIPE_BUF (4096 bytes
on Linux guarantees atomic append). Events > 4 KB are offloaded to
``<event_hash>.json`` sidecars (I10).

Fsync runs on a counter (every N events) and timer (every T ms). Both
default to ``100`` — small enough for crash consistency, large enough
that fsync is not on the hot path.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.spine.event_record import EventRecord


_ATOMIC_THRESHOLD = 4096  # Linux PIPE_BUF; do NOT change without kernel docs check
_DEFAULT_BATCH = 100
_DEFAULT_INTERVAL_MS = 100


class FileSink:
    """Append-only JSONL sink under ``<run_dir>/events.jsonl``."""

    def __init__(
        self,
        run_dir: Path,
        *,
        run_id: str,
        file_name: str = "events.jsonl",
        fsync_batch: int = _DEFAULT_BATCH,
        fsync_interval_ms: int = _DEFAULT_INTERVAL_MS,
    ) -> None:
        self._run_dir = Path(run_dir)
        self._run_id = run_id
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
