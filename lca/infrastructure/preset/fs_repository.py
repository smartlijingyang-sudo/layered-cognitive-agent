"""File system implementation of PresetRepositoryProtocol."""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.models.preset.package import AuthoredPlugin, PresetPackage, PresetScope
from lca.contracts.protocols.preset.repository import PresetRepositoryProtocol
from lca.infrastructure.path.locator import get_lca_home

_PRESET_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_preset_id(preset_id: str) -> None:
    """Validate preset_id against path-traversal and invalid naming attacks (INV-AP01)."""
    if not preset_id or not _PRESET_ID_REGEX.match(preset_id):
        raise ValueError(
            f"Invalid preset_id: {preset_id!r}. Must be non-empty alphanumeric with hyphens/underscores."
        )


class FileSystemPresetRepository(PresetRepositoryProtocol):
    """Repository storing PresetPackages in local filesystem scopes.

    Topology:
    - PRIVATE:  {assistant_home}/presets/{preset_id}/ (+ {assistant_home}/plugins/{name}.py)
    - SHARED:   {shared_root}/{preset_id}/
    - PLATFORM: {platform_root}/{preset_id}/
    """

    def __init__(
        self,
        *,
        shared_root: Path | None = None,
        platform_root: Path | None = None,
    ) -> None:
        self._shared_root = shared_root or (get_lca_home() / "shared" / "presets")
        self._platform_root = platform_root or (
            Path(__file__).resolve().parents[3] / "bundles" / "agent-presets"
        )

    def _resolve_dir(
        self,
        preset_id: str,
        scope: PresetScope,
        assistant_home: Path | None,
    ) -> Path:
        validate_preset_id(preset_id)
        if scope == PresetScope.PRIVATE:
            if assistant_home is None:
                raise ValueError("assistant_home is required for PRIVATE preset scope")
            return assistant_home / "presets" / preset_id
        if scope == PresetScope.SHARED:
            return self._shared_root / preset_id
        if scope == PresetScope.PLATFORM:
            return self._platform_root / preset_id
        raise ValueError(f"Unsupported PresetScope: {scope}")

    def save(self, package: PresetPackage, *, assistant_home: Path | None = None) -> Path:
        """Persist preset package to disk with plugins, bundle.yaml, and metadata."""
        validate_preset_id(package.preset_id)
        target_dir = self._resolve_dir(package.preset_id, package.scope, assistant_home)
        target_dir.mkdir(parents=True, exist_ok=True)

        plugins_dir = target_dir / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write plugin files
        for plugin in package.plugins:
            plugin_file = plugins_dir / f"{plugin.name}.py"
            plugin_file.write_text(plugin.code, encoding="utf-8")

            # Autonomous agent standalone access copy
            if package.scope == PresetScope.PRIVATE and assistant_home is not None:
                standalone_plugins_dir = assistant_home / "plugins"
                standalone_plugins_dir.mkdir(parents=True, exist_ok=True)
                (standalone_plugins_dir / f"{plugin.name}.py").write_text(
                    plugin.code, encoding="utf-8"
                )

        # 2. Write bundle.yaml
        bundle_manifest = (
            package.bundle_manifest
            if package.bundle_manifest
            else self._build_default_bundle_manifest(package)
        )
        bundle_yaml_path = target_dir / "bundle.yaml"
        _atomic_write_text(bundle_yaml_path, yaml.safe_dump(bundle_manifest, sort_keys=False))

        # 3. Write preset.json metadata
        metadata = {
            "preset_id": package.preset_id,
            "scope": package.scope.value,
            "assistant_id": package.assistant_id,
            "description": package.description,
            "created_at": package.created_at,
            "plugins": [
                {
                    "name": p.name,
                    "capabilities": list(p.capabilities),
                    "side_effects": p.side_effects,
                    "policy_class": p.policy_class,
                    "implements": list(p.implements),
                }
                for p in package.plugins
            ],
        }
        _atomic_write_text(
            target_dir / "preset.json", json.dumps(metadata, ensure_ascii=False, indent=2)
        )

        return target_dir

    def find_by_id(
        self,
        preset_id: str,
        *,
        assistant_home: Path | None = None,
        scope: PresetScope | None = None,
    ) -> PresetPackage | None:
        """Find and deserialize preset package by id across candidate scopes."""
        validate_preset_id(preset_id)

        candidates: list[tuple[PresetScope, Path]] = []
        if scope is not None:
            candidates.append(
                (scope, self._resolve_dir(preset_id, scope, assistant_home))
            )
        else:
            if assistant_home is not None:
                candidates.append(
                    (PresetScope.PRIVATE, assistant_home / "presets" / preset_id)
                )
            candidates.append((PresetScope.SHARED, self._shared_root / preset_id))
            candidates.append((PresetScope.PLATFORM, self._platform_root / preset_id))

        for cand_scope, cand_dir in candidates:
            if cand_dir.is_dir():
                return self._load_from_dir(preset_id, cand_scope, cand_dir)
        return None

    def list_presets(
        self,
        *,
        assistant_home: Path | None = None,
        scope: PresetScope | None = None,
    ) -> tuple[PresetPackage, ...]:
        """List all valid preset packages available to the given assistant or scope."""
        results: list[PresetPackage] = []
        seen_ids: set[str] = set()

        search_scopes: list[tuple[PresetScope, Path]] = []
        if (
            (scope is None or scope == PresetScope.PRIVATE)
            and assistant_home is not None
            and (assistant_home / "presets").is_dir()
        ):
            search_scopes.append((PresetScope.PRIVATE, assistant_home / "presets"))
        if (scope is None or scope == PresetScope.SHARED) and self._shared_root.is_dir():
            search_scopes.append((PresetScope.SHARED, self._shared_root))
        if (scope is None or scope == PresetScope.PLATFORM) and self._platform_root.is_dir():
            search_scopes.append((PresetScope.PLATFORM, self._platform_root))

        for target_scope, root_dir in search_scopes:
            for child in sorted(root_dir.iterdir()):
                if not child.is_dir() or child.name.startswith("."):
                    continue
                preset_id = child.name
                if preset_id in seen_ids:
                    continue
                try:
                    validate_preset_id(preset_id)
                except ValueError:
                    continue

                package = self._load_from_dir(preset_id, target_scope, child)
                if package is not None:
                    results.append(package)
                    seen_ids.add(preset_id)

        return tuple(results)

    def delete(
        self,
        preset_id: str,
        *,
        assistant_home: Path | None = None,
        scope: PresetScope = PresetScope.PRIVATE,
    ) -> bool:
        """Delete preset package from storage."""
        validate_preset_id(preset_id)
        target_dir = self._resolve_dir(preset_id, scope, assistant_home)
        if target_dir.is_dir():
            shutil.rmtree(target_dir)
            return True
        return False

    def _load_from_dir(
        self,
        preset_id: str,
        scope: PresetScope,
        preset_dir: Path,
    ) -> PresetPackage | None:
        bundle_file = preset_dir / "bundle.yaml"
        preset_json_file = preset_dir / "preset.json"
        plugins_dir = preset_dir / "plugins"

        if not bundle_file.is_file() and not preset_json_file.is_file() and not plugins_dir.is_dir():
            return None

        # Load metadata if exists
        meta: dict[str, Any] = {}
        if preset_json_file.is_file():
            with contextlib.suppress(Exception):
                meta = json.loads(preset_json_file.read_text(encoding="utf-8"))

        bundle_manifest: dict[str, Any] = {}
        if bundle_file.is_file():
            with contextlib.suppress(Exception):
                bundle_manifest = yaml.safe_load(bundle_file.read_text(encoding="utf-8")) or {}

        assistant_id = meta.get("assistant_id")
        description = meta.get("description", "")
        created_at = meta.get("created_at", 0.0)

        # Load plugins
        plugins: list[AuthoredPlugin] = []
        meta_plugins_dict = {p["name"]: p for p in meta.get("plugins", [])}

        if plugins_dir.is_dir():
            for py_file in sorted(plugins_dir.glob("*.py")):
                plugin_name = py_file.stem
                code = py_file.read_text(encoding="utf-8")
                p_meta = meta_plugins_dict.get(plugin_name, {})
                caps = tuple(p_meta.get("capabilities", ()))
                side_effects = p_meta.get("side_effects", "none")
                policy_class = p_meta.get("policy_class", "execute")

                plugins.append(
                    AuthoredPlugin(
                        name=plugin_name,
                        code=code,
                        path=str(py_file),
                        capabilities=caps,
                        side_effects=side_effects,
                        policy_class=policy_class,
                    )
                )

        return PresetPackage(
            preset_id=preset_id,
            scope=scope,
            assistant_id=assistant_id,
            description=description,
            plugins=tuple(plugins),
            bundle_manifest=bundle_manifest,
            created_at=created_at or 0.0,
        )

    def _build_default_bundle_manifest(self, package: PresetPackage) -> dict[str, Any]:
        plugin_entries = []
        for p in package.plugins:
            plugin_entries.append(
                {
                    "name": p.name,
                    "path": f"plugins/{p.name}.py",
                    "capabilities": list(p.capabilities),
                    "policy_class": p.policy_class,
                }
            )
        return {
            "bundle": {
                "name": f"preset_{package.preset_id}",
                "version": "1.0.0",
                "description": package.description or f"Preset {package.preset_id}",
            },
            "plugins": plugin_entries,
        }


def _atomic_write_text(file_path: Path, content: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=file_path.parent, delete=False, encoding="utf-8") as tf:
        tf.write(content)
        temp_name = tf.name
    shutil.move(temp_name, file_path)


__all__ = [
    "FileSystemPresetRepository",
    "validate_preset_id",
]
