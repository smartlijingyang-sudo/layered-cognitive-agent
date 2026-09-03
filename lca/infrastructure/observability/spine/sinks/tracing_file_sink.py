"""TracingFileSink — fail-loud ``FileSink`` wrapper.

The wrapper layers two extra safety nets on top of :class:`FileSink`:

- **Local fallback** (``<run_dir>/FALLBACK.log``) — when the underlying
  FileSink raises OSError (disk full, closed fd, etc.), a summary
  line lands in FALLBACK.log. The fallback file itself is wrapped;
  its failure escalates to structlog ERROR.
- **Optional legacy sidecar naming** (``legacy_sha256_only=True``)
  — emits ``<sha256>.json`` instead of ``<sha8>-<SafeClass>.json``
  for readers that depend on the legacy file name.

The normal ledger / exception index writes are delegated to
:class:`FileSink`. TracingFileSink only intercepts the failure mode
where FileSink itself raises, plus an ``exceptions_index_failed``
signal returned by :meth:`FileSink.write` when the index append
failed after the main ledger write succeeded.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import (
    FileSink,
    safe_class_name,
)
from lca.infrastructure.observability.spine.sinks.naming import (
    DEFAULT_SPINE_TEMPLATE,
    resolve_filename,
    spine_filename_for_run,
)

log = logging.getLogger(__name__)

_DEFAULT_BATCH = 100
_DEFAULT_INTERVAL_MS = 100


def _safe_class_name(exception_class: str) -> str:
    """Compatibility shim — historically defined in this module."""
    return safe_class_name(exception_class)


class TracingFileSink:
    """Fail-loud :class:`FileSink` wrapper with fallback logging."""

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
        if spine_filename or file_name == DEFAULT_SPINE_TEMPLATE:
            file_name = spine_filename_for_run(run_id)
        else:
            file_name = resolve_filename(file_name, run_id)
        self._legacy_sha256_only = legacy_sha256_only
        self._fallback_path = self._run_dir / "FALLBACK.log"
        self._closed = False

        self._main = FileSink(
            self._run_dir,
            run_id=run_id,
            file_name=file_name,
            exceptions_file_name=exceptions_file_name,
            fsync_batch=fsync_batch,
            fsync_interval_ms=fsync_interval_ms,
            spine_filename=spine_filename,
            legacy_sha256_only=legacy_sha256_only,
        )

    @property
    def path(self) -> Path:
        return self._main.path

    @property
    def exceptions_path(self) -> Path | None:
        return self._main.exceptions_path

    @property
    def exceptions_count(self) -> int:
        return self._main.exceptions_count

    def write(self, record: EventRecord) -> None:
        if self._closed:
            self._write_fallback(record, reason="sink_closed")
            return
        try:
            index_reason = self._main.write(record)
        except Exception as exc:
            self._write_fallback(record, reason=f"main_failed:{exc!r}")
            return
        # FileSink returns a token if its exception index append failed.
        # Fall back via FALLBACK.log so a broken index fd never loses data.
        if index_reason is not None:
            self._write_fallback(record, reason=index_reason)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._main.close()
        except Exception as exc:
            log.error(
                "tracing_sink: main.close failed run_id=%s err=%s",
                self._run_id,
                exc,
            )

    def _write_fallback(self, record: EventRecord, *, reason: str) -> None:
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
            with self._fallback_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception as exc:
            log.error(
                "tracing_sink: FALLBACK write FAILED run_id=%s ep=%s reason=%s err=%s",
                self._run_id,
                record.execution_point,
                reason,
                exc,
                extra={
                    "run_id": self._run_id,
                    "execution_point": record.execution_point,
                    "fallback_reason": reason,
                    "exception_class": str(record.payload.get("exception_class", "?")),
                },
            )


def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"_type": type(payload).__name__}
    return {
        "exception_class": payload.get("exception_class"),
        "exception_message": payload.get("exception_message"),
        "boundary": payload.get("boundary"),
        "source_location": payload.get("source_location"),
    }


__all__ = ["TracingFileSink", "_safe_class_name"]
