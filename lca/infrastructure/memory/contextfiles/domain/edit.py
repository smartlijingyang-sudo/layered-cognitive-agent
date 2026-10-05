"""Read-before-write staleness guard for memory file edits (forwarded to contextfiles.sync)."""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.sync import (
    FileVersion,
    StaleSnapshotOperationError,
    require_fresh,
)

__all__ = ["FileVersion", "StaleSnapshotOperationError", "require_fresh"]
