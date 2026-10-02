"""Read-before-write staleness guard for memory file edits (INV-READ-BEFORE-WRITE).

A durable memory edit must be based on the latest disk content. The caller
snapshots the file before reading and again before writing; if the file moved
in between, the edit is refused instead of silently clobbering a concurrent
change. The guard is pure: the caller supplies both snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass


class StaleSnapshotOperationError(RuntimeError):
    """Raised when a memory edit targets a file that changed since the read."""


@dataclass(frozen=True, slots=True)
class FileVersion:
    """One file's identity: path and mtime ns."""

    path: str
    mtime_ns: int


def require_fresh(expected: FileVersion | None, current: FileVersion | None) -> None:
    """Raise when ``current`` differs from the version ``expected`` was read at.

    A missing file at either side is treated as an empty version and only
    conflicts when the other side reports a real file.
    """

    if current is None:
        if expected is None:
            return
        raise StaleSnapshotOperationError(f"file disappeared during edit: {expected.path}")
    if expected is None:
        raise StaleSnapshotOperationError(f"file appeared during edit: {current.path}")
    if expected.path != current.path or expected.mtime_ns != current.mtime_ns:
        raise StaleSnapshotOperationError(
            f"file changed during edit: {expected.path} (mtime {expected.mtime_ns} -> {current.mtime_ns})"
        )


__all__ = ["FileVersion", "StaleSnapshotOperationError", "require_fresh"]
