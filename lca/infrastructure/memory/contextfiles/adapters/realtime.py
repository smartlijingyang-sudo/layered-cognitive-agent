"""Real-time standing-file watcher (ADR-0254 continuous control plane).

A background thread polls one assistant home's standing files every
``interval_s`` and captures the unified diff at detection time, so the next
context assembly sees the change without a synchronous diff against a stale
baseline. Faults are contained: a failing poll is logged, the pending buffer
stays intact, and the session keeps assembling. The poll-based cursor remains
the fallback when no watcher is registered.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from pathlib import Path

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.events.publisher import WatcherFault
from lca.infrastructure.memory.contextfiles.ports.events import DomainEventPublisher
from lca.infrastructure.memory.contextfiles.service.watch import StandingCursor

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_S = 0.5


class RealTimeStandingWatcher:
    """One background watcher per assistant home."""

    def __init__(
        self,
        home_path: str | Path,
        *,
        interval_s: float = _DEFAULT_INTERVAL_S,
        publisher: DomainEventPublisher | None = None,
    ) -> None:
        self._home_path = str(Path(home_path).resolve())
        self._interval_s = max(0.05, float(interval_s))
        self._layout = layout_for_home(self._home_path)
        self._cursor = StandingCursor(publisher)
        self._store = DiskFileStore(self._home_path)
        self._pending: deque[str] = deque()
        self._faults: deque[str] = deque()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._publisher = publisher

    def start(self) -> None:
        """Start the background polling thread once."""

        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"standing-watch-{self._home_path}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background thread and drain pending diffs."""

        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(self._interval_s * 2, 0.2))
        self._thread = None

    def consume(self) -> str:
        """Return and clear every diff captured since the last consume."""

        with self._lock:
            if not self._pending:
                return ""
            parts = list(self._pending)
            self._pending.clear()
        return "\n\n".join(parts)

    @property
    def faults(self) -> tuple[str, ...]:
        """Diagnostic WATCHER_FAULT lines captured since start."""

        with self._lock:
            return tuple(self._faults)

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval_s):
            try:
                self._poll_once()
            except Exception as exc:
                self._record_fault(exc)

    def _record_fault(self, exc: BaseException) -> None:
        logger.exception("WATCHER_FAULT home=%s error=%s", self._home_path, exc)
        with self._lock:
            self._faults.append(f"WATCHER_FAULT {type(exc).__name__}: {exc}")
        if self._publisher is not None:
            self._publisher.publish(WatcherFault(home=self._home_path, error=type(exc).__name__))

    def _poll_once(self) -> None:
        diff = self._cursor.poll(self._store, standing_files=self._layout.standing_files)
        if not diff:
            return
        with self._lock:
            self._pending.append(diff)
        logger.info("standing watcher captured diff home=%s", self._home_path)


class FaultInjectingWatcher(RealTimeStandingWatcher):
    """Test seam: raises on every poll to exercise fault containment."""

    def _poll_once(self) -> None:
        raise OSError("injected watcher fault")


__all__ = ["FaultInjectingWatcher", "RealTimeStandingWatcher"]
