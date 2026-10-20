"""TrashManager — Recoverable soft-delete repository for workspace files (.trash/).

The delete ritual itself is owned by the FileStore.delete seam (RA-176);
this manager is the path-addressed adapter over it, plus restore and TTL
purge over the .trash/ sidecars.

Implements:
1. Recoverable soft-deletion retaining original relative paths and timestamps (INV-FS-07),
   via the FileStore.delete seam (move+sidecar+flag ritual owned by the store).
2. Restore from .trash/ sidecars; 30-day automated TTL expiration and purging (INV-FS-08).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lca.infrastructure.file.store import FileStore, trash_dir_for


class TrashManager:
    """Path-addressed soft-delete adapter over the FileStore delete seam."""

    def __init__(
        self,
        workspace_root: Path | str,
        registry: Any = None,
        store: FileStore | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._trash_dir = trash_dir_for(self._workspace_root)
        self._registry = registry
        self._store = store

    @property
    def trash_dir(self) -> Path:
        return self._trash_dir

    def trash_file(self, rel_path: str) -> bool:
        """Soft-delete a workspace file through the FileStore.delete seam.

        Only resolves the path to an attachment id; the move+sidecar+flag
        ritual lives in the store (RA-176). Requires store=... — fail-loud:
        the old standalone hand-rolled ritual was the bypass this seam
        removes, so there is no silent fallback to it.
        """
        if self._store is None:
            raise RuntimeError(
                "TrashManager.trash_file requires a FileStore (pass store=...); "
                "the standalone trash ritual was removed in RA-176."
            )
        clean_rel = rel_path.replace("\\", "/").lstrip("/")
        record = self._registry.get_by_path(clean_rel) if self._registry is not None else None
        if record is None:
            return False
        return self._store.delete(record.file_id)

    def restore_file(self, rel_path: str) -> bool:
        """Restore a trashed file back to its exact original workspace path."""
        clean_rel = rel_path.replace("\\", "/").lstrip("/")
        dest = (self._workspace_root / clean_rel).resolve()

        # Find matching item in trash by orig_rel_path
        for meta_file in self._trash_dir.glob("*.meta.json"):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if data.get("orig_rel_path") == clean_rel:
                trash_id = data["trash_id"]
                blob_path = self._trash_dir / f"{trash_id}.blob"
                if not blob_path.is_file():
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(blob_path), str(dest))
                meta_file.unlink(missing_ok=True)

                if self._registry is not None:
                    self._registry.clear_trashed(clean_rel)

                return True

        return False

    def purge_expired(self, ttl_seconds: int = 30 * 86400) -> int:
        """Physically unlink items whose trashed_at age exceeds ttl_seconds."""
        now = datetime.now(timezone.utc)
        purged = 0
        for meta_file in list(self._trash_dir.glob("*.meta.json")):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                trashed_at = datetime.fromisoformat(data["trashed_at"])
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                continue

            age_seconds = (now - trashed_at).total_seconds()
            if age_seconds > ttl_seconds:
                trash_id = data.get("trash_id")
                blob_path = self._trash_dir / f"{trash_id}.blob"
                blob_path.unlink(missing_ok=True)
                meta_file.unlink(missing_ok=True)
                purged += 1

        return purged


__all__ = ["TrashManager"]
