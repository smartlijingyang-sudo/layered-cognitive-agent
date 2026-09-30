"""Process-local standing-file cursor, one per assistant home.

History assembly is read-only toward agent state, so the previous copy stays
in this process instead of a file under the home. A different watcher can
replace ``poll_standing_home`` and still return the same diff text.
"""

from __future__ import annotations

import threading

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.service.watch import StandingCursor

_cursors: dict[str, StandingCursor] = {}
_lock = threading.Lock()


def poll_standing_home(home_path: str) -> str:
    """Diff the standing files in ``home_path`` against this process's last copy."""

    with _lock:
        cursor = _cursors.setdefault(home_path, StandingCursor())
        return cursor.poll(DiskFileStore(home_path))


def reset_standing_cursors() -> None:
    """Drop every cursor. Tests use this so homes do not leak across cases."""

    with _lock:
        _cursors.clear()


__all__ = ["poll_standing_home", "reset_standing_cursors"]
