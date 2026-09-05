"""Atomic JSON snapshot sink — write-behind target for whole-file caches.

Used by projection cache (``*.projcache.json``): each batch item is one
full document; ``append_batch`` coalesces duplicate paths (last wins) and
writes via temp file + ``os.replace`` (crash-safe, no torn reads).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lca.infrastructure.persistence.write_behind import WriteBehindSink


@dataclass(frozen=True, slots=True)
class AtomicJsonSnapshot:
    """One whole-file JSON snapshot pending write."""

    path: Path
    encoded: str


class AtomicJsonFileSink(WriteBehindSink):
    """Batch-write JSON documents atomically (one replace per path)."""

    def append_batch(self, events: Sequence[AtomicJsonSnapshot]) -> None:
        if not events:
            return
        coalesced: dict[Path, str] = {}
        for item in events:
            coalesced[item.path] = item.encoded
        for path, encoded in coalesced.items():
            _write_atomic(path, encoded)

    def close(self) -> None:
        return


def _write_atomic(path: Path, encoded: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(encoded, encoding="utf-8")
    os.replace(tmp, path)


__all__ = ["AtomicJsonFileSink", "AtomicJsonSnapshot"]
