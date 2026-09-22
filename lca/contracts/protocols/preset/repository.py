"""Repository protocol for PresetPackage storage and retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from lca.contracts.models.preset.package import PresetPackage, PresetScope


@runtime_checkable
class PresetRepositoryProtocol(Protocol):
    """Abstract repository for persisting and querying PresetPackages across scopes."""

    def save(self, package: PresetPackage, *, assistant_home: Path | None = None) -> Path:
        """Persist preset package to disk under appropriate scope topology."""
        ...

    def find_by_id(
        self,
        preset_id: str,
        *,
        assistant_home: Path | None = None,
        scope: PresetScope | None = None,
    ) -> PresetPackage | None:
        """Find and deserialize preset package by id."""
        ...

    def list_presets(
        self,
        *,
        assistant_home: Path | None = None,
        scope: PresetScope | None = None,
    ) -> tuple[PresetPackage, ...]:
        """List all valid preset packages available to the given assistant or scope."""
        ...

    def delete(
        self,
        preset_id: str,
        *,
        assistant_home: Path | None = None,
        scope: PresetScope = PresetScope.PRIVATE,
    ) -> bool:
        """Delete preset package from storage. Returns True if deleted, False if not found."""
        ...


__all__ = ["PresetRepositoryProtocol"]
