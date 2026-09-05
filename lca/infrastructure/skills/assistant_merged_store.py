"""Merge global operational skills with an assistant Home overlay (ADR-0187)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lca.contracts.protocols.memory.operational_skills import (
    SkillIndexEntry,
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)
from lca.infrastructure.skills.disk_store import DiskSkillPackageStore
from lca.infrastructure.skills.settings import SkillSettings

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.skill_overlay import AssistantSkillOverlay


class AssistantMergedSkillStore(SkillPackageStore):
    """Read-through view: assistant Home skills + global ``~/.lca/skills/``.

    Writes stay on ``AssistantSkillOverlay`` / global importer — this adapter
    is for prompt discovery and ``activate_skill`` lookup only.
    """

    def __init__(
        self,
        *,
        global_store: SkillPackageStore,
        overlay: AssistantSkillOverlay,
        assistant_id: str,
    ) -> None:
        self._global = global_store
        self._overlay = overlay
        self._assistant_id = assistant_id
        self._assistant_store: DiskSkillPackageStore | None = None

    def _assistant_disk_store(self) -> DiskSkillPackageStore | None:
        if self._assistant_store is not None:
            return self._assistant_store
        receipts = self._overlay.list_installed(self._assistant_id)
        if not receipts:
            return None
        skills_root = Path(receipts[0].install_path).parent
        if not skills_root.is_dir():
            return None
        self._assistant_store = DiskSkillPackageStore(SkillSettings(cache_dir=skills_root))
        return self._assistant_store

    def list_installed(self) -> tuple[SkillIndexEntry, ...]:
        seen: set[str] = set()
        merged: list[SkillIndexEntry] = []
        assistant_store = self._assistant_disk_store()
        if assistant_store is not None:
            for entry in assistant_store.list_installed():
                if entry.skill_id in seen:
                    continue
                seen.add(entry.skill_id)
                merged.append(entry)
        for entry in self._global.list_installed():
            if entry.skill_id in seen:
                continue
            seen.add(entry.skill_id)
            merged.append(entry)
        return tuple(merged)

    def get(self, skill_id: str) -> SkillPackage:
        assistant_store = self._assistant_disk_store()
        if assistant_store is not None:
            try:
                return assistant_store.get(skill_id)
            except SkillNotFoundError:
                pass
        return self._global.get(skill_id)

    def read_resource(self, skill_id: str, rel_path: str) -> str:
        assistant_store = self._assistant_disk_store()
        if assistant_store is not None:
            try:
                return assistant_store.read_resource(skill_id, rel_path)
            except SkillNotFoundError:
                pass
        return self._global.read_resource(skill_id, rel_path)

    def resource_files(self, skill_id: str) -> dict[str, bytes]:
        assistant_store = self._assistant_disk_store()
        if assistant_store is not None:
            try:
                return assistant_store.resource_files(skill_id)
            except SkillNotFoundError:
                pass
        return self._global.resource_files(skill_id)


__all__ = ["AssistantMergedSkillStore"]
