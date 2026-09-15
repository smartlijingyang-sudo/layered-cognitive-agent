"""Merge global operational skills with an assistant Home overlay (ADR-0187)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from lca.contracts.protocols.memory.operational_skills import (
    SkillIndexEntry,
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.skill_overlay import AssistantSkillOverlay

_T = TypeVar("_T")


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

    def _lookup(self, fetch: Callable[[SkillPackageStore], _T]) -> _T:
        """Read the assistant scope first, then the global scope.

        A miss in the assistant scope is not an error — the skill may simply be
        a global one — so it falls through to the global store, whose own
        ``SkillNotFoundError`` is the single authoritative failure the caller
        sees.
        """
        assistant_store = self._assistant_disk_store()
        if assistant_store is not None:
            try:
                return fetch(assistant_store)
            except SkillNotFoundError:  # WHY: assistant scope is only one of two
                pass  # lookup scopes; the global store below decides.
        return fetch(self._global)

    def get(self, skill_id: str) -> SkillPackage:
        return self._lookup(lambda store: store.get(skill_id))

    def read_resource(self, skill_id: str, rel_path: str) -> str:
        return self._lookup(lambda store: store.read_resource(skill_id, rel_path))

    def resource_files(self, skill_id: str) -> dict[str, bytes]:
        return self._lookup(lambda store: store.resource_files(skill_id))


__all__ = ["AssistantMergedSkillStore"]
