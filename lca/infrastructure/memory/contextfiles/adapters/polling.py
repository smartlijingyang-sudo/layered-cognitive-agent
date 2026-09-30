"""Process-local standing-file cursor and real-time watcher registry.

History assembly is read-only toward agent state, so the previous copy stays
in this process instead of a file under the home. A registered real-time
watcher captures diffs at detection time; ``poll_standing_home`` then returns
those captured diffs on the next assembly. Without a watcher the synchronous
cursor remains the fallback and still returns the same diff text.
"""

from __future__ import annotations

import threading

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.adapters.realtime import RealTimeStandingWatcher
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.service.watch import StandingCursor

_cursors: dict[str, StandingCursor] = {}
_watchers: dict[str, RealTimeStandingWatcher] = {}
_lock = threading.Lock()


def poll_standing_home(home_path: str) -> str:
    """Diff the standing files in ``home_path`` against the last copy.

    When a real-time watcher is registered for this home, the diffs it
    captured since the previous assembly are returned. Otherwise a
    synchronous cursor polls on demand.
    """

    with _lock:
        watcher = _watchers.get(home_path)
    if watcher is not None:
        return watcher.consume()
    layout = layout_for_home(home_path)
    with _lock:
        cursor = _cursors.setdefault(home_path, StandingCursor())
        return cursor.poll(DiskFileStore(home_path), standing_files=layout.standing_files)


def ensure_standing_watcher(
    home_path: str,
    *,
    interval_s: float = 0.5,
) -> RealTimeStandingWatcher:
    """Start a real-time watcher for ``home_path`` and return it."""

    with _lock:
        watcher = _watchers.get(home_path)
        if watcher is None:
            watcher = RealTimeStandingWatcher(home_path, interval_s=interval_s)
            _watchers[home_path] = watcher
        watcher.start()
        return watcher


def reset_standing_cursors() -> None:
    """Drop every cursor and stop every watcher. Tests use this."""

    global _watchers
    with _lock:
        for watcher in _watchers.values():
            watcher.stop()
        _watchers = {}
        _cursors.clear()


__all__ = ["ensure_standing_watcher", "poll_standing_home", "reset_standing_cursors"]
