"""File access port for the context-files architecture.

``FileStore`` abstracts all disk I/O the context-files domain needs so the
domain and its services never depend on a concrete filesystem. A different
backend (in-memory, sandboxed, remote) can replace ``DiskFileStore`` without
touching domain logic. Paths are relative to a home root, so the same store
can serve any assistant directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    """One file's identity, size and mtime — the minimal stat a watcher needs."""

    path: str
    size_bytes: int
    mtime_ns: int


@runtime_checkable
class FileStore(Protocol):
    """Read, write, inspect and atomically replace files under a home root."""

    def read_text(self, relative_path: str) -> str: ...
    def write_text(self, relative_path: str, text: str) -> None: ...
    def atomic_replace(self, relative_path: str, text: str) -> None: ...
    def exists(self, relative_path: str) -> bool: ...
    def list_dir(self, relative_path: str) -> tuple[str, ...]: ...
    def snapshot(self, relative_path: str) -> FileSnapshot | None: ...


__all__ = ["FileSnapshot", "FileStore"]
