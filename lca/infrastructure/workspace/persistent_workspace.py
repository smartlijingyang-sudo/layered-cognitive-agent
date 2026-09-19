"""Persistent per-assistant workspace files (ADR-0244 D7.2).

The assistant Home scaffolds ``{home}/workspace/`` at creation time. This
service provides plain-file read/write/list access rooted strictly at that
directory. Workspace files are NOT part of the manifest digest (I-A13),
matching the memory layer behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

_WORKSPACE_DIR = "workspace"


class PersistentWorkspace(Protocol):
    """A durable workspace rooted at ``{home}/workspace/``."""

    def read(self, rel_path: str) -> bytes: ...

    def write(self, rel_path: str, data: bytes) -> None: ...

    def read_text(self, rel_path: str) -> str: ...

    def write_text(self, rel_path: str, text: str) -> None: ...

    def list(self) -> list[str]: ...


class _LocalPersistentWorkspace:
    """Filesystem-backed workspace with a path-traversal guard."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, rel_path: str) -> Path:
        root = self._root.resolve()
        target = (self._root / rel_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"workspace path escapes root: {rel_path}")
        return target

    def read(self, rel_path: str) -> bytes:
        return self._resolve(rel_path).read_bytes()

    def write(self, rel_path: str, data: bytes) -> None:
        target = self._resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def read_text(self, rel_path: str) -> str:
        return self.read(rel_path).decode("utf-8")

    def write_text(self, rel_path: str, text: str) -> None:
        self.write(rel_path, text.encode("utf-8"))

    def list(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(
            str(path.relative_to(self._root)) for path in self._root.rglob("*") if path.is_file()
        )


class WorkspaceService:
    """Creates per-assistant ``PersistentWorkspace`` rooted at ``{home}/workspace/``."""

    def open(self, assistant_id: str, home_path: str | Path) -> PersistentWorkspace:
        """Open (and create if needed) the workspace for one assistant Home."""
        del assistant_id  # isolation comes from the home_path root itself
        return _LocalPersistentWorkspace(Path(home_path) / _WORKSPACE_DIR)


__all__ = ["PersistentWorkspace", "WorkspaceService"]
