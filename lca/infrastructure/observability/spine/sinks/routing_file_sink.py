"""Run-routing FileSink — boot vs per-run events.jsonl (ADR-0165.1 layout).

Boot / no-run events → ``boot_path`` (default ``.lca/spine/boot-events.jsonl``).
Events with a real ``run_id`` → ``<runs_root>/<run_id>/events.jsonl``.
"""

from __future__ import annotations

import threading
from pathlib import Path

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink

_BOOT_RUN_IDS = frozenset({"", "boot", "default-run"})


class RunRoutingFileSink:
    """Demux EventRecords to boot file or per-run ``events.jsonl``."""

    def __init__(
        self,
        *,
        boot_path: Path,
        runs_root: Path,
        file_name: str = "events.jsonl",
        spine_filename: bool = False,
    ) -> None:
        self._boot_path = Path(boot_path)
        self._runs_root = Path(runs_root)
        self._file_name = file_name
        self._spine_filename = spine_filename
        self._boot_path.parent.mkdir(parents=True, exist_ok=True)
        self._runs_root.mkdir(parents=True, exist_ok=True)
        self._boot = FileSink(
            self._boot_path.parent,
            run_id="boot",
            file_name=self._boot_path.name,
        )
        self._runs: dict[str, FileSink] = {}
        self._lock = threading.Lock()
        self._closed = False

    @property
    def boot_path(self) -> Path:
        return self._boot.path

    @property
    def runs_root(self) -> Path:
        return self._runs_root

    def path_for(self, run_id: str) -> Path:
        """Return the events.jsonl path for a run (may not exist yet)."""
        if self._is_boot_run_id(run_id):
            return self._boot.path
        return self._runs_root / run_id / self._file_name

    def write(self, record: EventRecord) -> None:
        if self._closed:
            raise RuntimeError("RunRoutingFileSink already closed")
        run_id = str(record.run_id or "")
        if self._is_boot_run_id(run_id):
            self._boot.write(record)
            return
        sink = self._sink_for(run_id)
        sink.write(record)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            sinks = list(self._runs.values())
            self._runs.clear()
        self._boot.close()
        for sink in sinks:
            sink.close()

    def _sink_for(self, run_id: str) -> FileSink:
        with self._lock:
            existing = self._runs.get(run_id)
            if existing is not None:
                return existing
            run_dir = self._runs_root / run_id
            sink = FileSink(
                run_dir,
                run_id=run_id,
                file_name=self._file_name,
                spine_filename=self._spine_filename,
            )
            self._runs[run_id] = sink
            return sink

    @staticmethod
    def _is_boot_run_id(run_id: str) -> bool:
        return run_id in _BOOT_RUN_IDS


__all__ = ["RunRoutingFileSink"]
