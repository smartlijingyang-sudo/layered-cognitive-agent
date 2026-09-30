"""Default filesystem adapter for the ``FileStore`` port.

Resolves every relative path against a home root and rejects paths that would
escape it. Writes use a same-directory temporary file plus ``os.replace`` so a
crash never leaves a half-written standing file.
"""

from __future__ import annotations

import os
from pathlib import Path

from lca.infrastructure.memory.contextfiles.ports.file_store import FileSnapshot


class DiskFileStore:
    """``FileStore`` backed by the local filesystem under one root directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, relative_path: str) -> Path:
        target = (self._root / relative_path).resolve()
        if target != self._root and self._root not in target.parents:
            raise ValueError(f"path escapes home root: {relative_path}")
        return target

    def read_text(self, relative_path: str) -> str:
        return self._resolve(relative_path).read_text(encoding="utf-8")

    def write_text(self, relative_path: str, text: str) -> None:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def atomic_replace(self, relative_path: str, text: str) -> None:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)

    def exists(self, relative_path: str) -> bool:
        return self._resolve(relative_path).is_file()

    def list_dir(self, relative_path: str) -> tuple[str, ...]:
        directory = self._resolve(relative_path)
        if not directory.is_dir():
            return ()
        return tuple(entry.name for entry in sorted(directory.iterdir()))

    def snapshot(self, relative_path: str) -> FileSnapshot | None:
        target = self._resolve(relative_path)
        try:
            stat = target.stat()
        except OSError:
            return None
        return FileSnapshot(
            path=relative_path,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
        )


__all__ = ["DiskFileStore"]
