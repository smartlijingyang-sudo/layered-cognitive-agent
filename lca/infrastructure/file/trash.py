"""TrashManager — Recoverable soft-delete repository for workspace files (.trash/).

Implements:
1. Recoverable soft-deletion retaining original relative paths and timestamps (INV-FS-07).
2. Metadata sidecars (.meta.json + .blob) with SQLite index synchronization.
3. 30-day automated TTL expiration and purging (INV-FS-08).
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lca.contracts.atoms.ids.ids import new_id


class TrashManager:
    """Manages soft-deleted workspace files in the .trash/ directory."""

    def __init__(self, workspace_root: Path | str, registry: Any = None) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        if self._workspace_root.name == "workspace":
            self._trash_dir = self._workspace_root.parent / ".trash"
        else:
            self._trash_dir = self._workspace_root / ".trash"
        self._trash_dir.mkdir(parents=True, exist_ok=True)
        self._registry = registry

    @property
    def trash_dir(self) -> Path:
        return self._trash_dir

    def trash_file(self, rel_path: str) -> bool:
        """Move a file to .trash/ and mark it trashed in the index."""
        clean_rel = rel_path.replace("\\", "/").lstrip("/")
        target = (self._workspace_root / clean_rel).resolve()
        if not target.is_file():
            return False

        now = datetime.now(timezone.utc)
        trash_id = new_id("trash")
        blob_path = self._trash_dir / f"{trash_id}.blob"
        meta_path = self._trash_dir / f"{trash_id}.meta.json"

        meta = {
            "trash_id": trash_id,
            "orig_rel_path": clean_rel,
            "trashed_at": now.isoformat(),
            "size_bytes": target.stat().st_size,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.move(str(target), str(blob_path))

        if self._registry is not None:
            self._registry.mark_trashed(clean_rel, now)

        return True

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
