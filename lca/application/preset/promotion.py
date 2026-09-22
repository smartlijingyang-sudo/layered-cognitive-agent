"""Application service for promoting presets to shared and platform scopes."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

from lca.contracts.models.observability.diagnostic.diagnostic import (
    DiagnosticCategory,
    DiagnosticStatus,
)
from lca.contracts.models.observability.event.event import OperationOutcome, RuntimeKind
from lca.contracts.models.observability.journal.journal import RuntimeObserved
from lca.contracts.models.preset.package import PresetPackage, PresetScope
from lca.contracts.protocols.preset.repository import PresetRepositoryProtocol
from lca.infrastructure.observability import record, record_runtime
from lca.infrastructure.preset.fs_repository import FileSystemPresetRepository

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Result of a preset promotion or export operation."""

    preset_id: str
    scope: PresetScope
    target_path: Path
    checksum: str


class PresetPromotionService:
    """Coordinates preset promotion between private, shared, and platform scopes."""

    def __init__(
        self,
        repository: PresetRepositoryProtocol | None = None,
        *,
        shared_root: Path | None = None,
        platform_root: Path | None = None,
    ) -> None:
        self._repo = repository or FileSystemPresetRepository(
            shared_root=shared_root, platform_root=platform_root
        )
        self._shared_root = shared_root
        self._platform_root = platform_root

    def promote_to_shared(
        self,
        preset_id: str,
        *,
        assistant_home: Path | str,
        author_id: str | None = None,
    ) -> PromotionResult:
        """Promote a private assistant preset to the shared library.

        Enables other agents in the workspace to discover and load the preset
        with immutable checksum verification.
        """
        home = Path(assistant_home)
        pkg = self._repo.find_by_id(preset_id, assistant_home=home, scope=PresetScope.PRIVATE)
        if pkg is None:
            raise FileNotFoundError(f"Private preset {preset_id!r} not found in {home}")

        checksum = self._calculate_checksum(pkg)
        shared_pkg = PresetPackage(
            preset_id=pkg.preset_id,
            scope=PresetScope.SHARED,
            assistant_id=author_id or pkg.assistant_id,
            description=pkg.description,
            plugins=pkg.plugins,
            bundle_manifest=pkg.bundle_manifest,
            created_at=pkg.created_at,
        )

        target_dir = self._repo.save(shared_pkg)

        # Update metadata with checksum and promotion details
        meta_path = target_dir / "preset.json"
        meta: dict[str, object] = {}
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["checksum"] = checksum
        meta["author_id"] = author_id or pkg.assistant_id
        meta["promoted_at"] = time.time()
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        # Record observability facts
        try:
            record_runtime(
                DiagnosticCategory.TOOL,
                "creator.preset_shared",
                plugin=preset_id,
                attributes={
                    "source_asst": str(pkg.assistant_id),
                    "shared_path": str(target_dir),
                    "checksum": checksum,
                },
                status=DiagnosticStatus.SUCCEEDED,
            )
            record(
                RuntimeObserved(
                    kind=RuntimeKind.PLUGIN,
                    operation="preset.shared",
                    source=preset_id,
                    outcome=OperationOutcome.SUCCESS,
                    input={
                        "preset_id": preset_id,
                        "source_asst": pkg.assistant_id,
                        "shared_path": str(target_dir),
                    },
                )
            )
        except Exception:
            _log.debug("preset_promotion.record_audit_skipped", preset_id=preset_id)

        return PromotionResult(
            preset_id=preset_id,
            scope=PresetScope.SHARED,
            target_path=target_dir,
            checksum=checksum,
        )

    def export_to_platform(
        self,
        preset_id: str,
        *,
        assistant_home: Path | str | None = None,
    ) -> PromotionResult:
        """Export an assistant preset to system platform bundles."""
        home = Path(assistant_home) if assistant_home else None
        pkg = self._repo.find_by_id(preset_id, assistant_home=home)
        if pkg is None:
            raise FileNotFoundError(f"Preset {preset_id!r} not found for export")

        checksum = self._calculate_checksum(pkg)
        platform_pkg = PresetPackage(
            preset_id=pkg.preset_id,
            scope=PresetScope.PLATFORM,
            assistant_id=pkg.assistant_id,
            description=pkg.description,
            plugins=pkg.plugins,
            bundle_manifest=pkg.bundle_manifest,
            created_at=pkg.created_at,
        )

        target_dir = self._repo.save(platform_pkg)

        try:
            record_runtime(
                DiagnosticCategory.TOOL,
                "creator.preset_exported",
                plugin=preset_id,
                attributes={
                    "export_path": str(target_dir),
                    "checksum": checksum,
                },
                status=DiagnosticStatus.SUCCEEDED,
            )
        except Exception:
            _log.debug("preset_promotion.record_audit_skipped", preset_id=preset_id)
        return PromotionResult(
            preset_id=preset_id,
            scope=PresetScope.PLATFORM,
            target_path=target_dir,
            checksum=checksum,
        )

    def _calculate_checksum(self, pkg: PresetPackage) -> str:
        hasher = hashlib.sha256()
        hasher.update(pkg.preset_id.encode("utf-8"))
        for plugin in sorted(pkg.plugins, key=lambda p: p.name):
            hasher.update(plugin.name.encode("utf-8"))
            hasher.update(plugin.code.encode("utf-8"))
        return hasher.hexdigest()


__all__ = [
    "PresetPromotionService",
    "PromotionResult",
]
