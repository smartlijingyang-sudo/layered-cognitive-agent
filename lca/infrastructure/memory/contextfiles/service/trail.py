"""Append-only daily trail writer (INV-EFFECT-GATEWAY-TRAIL-APPEND-ONLY).

The daily trail file ``memory/YYYY-MM-DD.md`` is raw evidence: it is
append-only and never rewritten. The shipped API only appends. An explicit
overwrite attempt raises :class:`NarrowGateViolationError` so a caller cannot
silently drop history.
"""

from __future__ import annotations

from lca.infrastructure.memory.contextfiles.domain.layout import ContextLayout, packaged_layout
from lca.infrastructure.memory.contextfiles.domain.trail import NarrowGateViolationError
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore


class TrailWriter:
    """Append-only writer for ``memory/YYYY-MM-DD.md``."""

    def __init__(
        self,
        store: FileStore,
        *,
        layout: ContextLayout | None = None,
    ) -> None:
        self._store = store
        self._layout = packaged_layout() if layout is None else layout

    def append(self, date: str, content: str) -> str:
        """Append one bullet to the trail file for ``date``. Returns the path."""

        relative = self.trail_path(date)
        existing = self._read(relative)
        line = content.strip()
        if not line:
            return relative
        if existing.strip():
            base = existing if existing.endswith("\n") else f"{existing}\n"
            body = f"{base}- {line}\n"
        else:
            body = f"# {date}\n\n- {line}\n"
        self._store.atomic_replace(relative, body)
        return relative

    def overwrite(self, date: str, content: str) -> str:
        """Always refused: trail files are append-only evidence."""

        del date, content
        raise NarrowGateViolationError(
            "trail files are append-only evidence; overwriting is not allowed"
        )

    def trail_path(self, date: str) -> str:
        """Relative path of one day's trail file."""

        return f"{self._layout.trail_dir}/{date}.md"

    def _read(self, relative: str) -> str:
        try:
            return self._store.read_text(relative)
        except OSError:
            return ""


__all__ = ["NarrowGateViolationError", "TrailWriter"]
