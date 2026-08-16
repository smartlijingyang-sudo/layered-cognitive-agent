"""Profile composition — YAML bundle expansion + patch + module resolution.

Mirrors DSH ``vendor/include/``:
- Read profile YAML → extract bundle list + patch list
- Expand bundles: append each bundle's ``insert`` entries in order
- Apply patch: by-id config replacement (shallow) + insert new entries
- Resolve modules: import ``name`` paths → resolved ``module`` objects

Depends on: ``loader/`` (PluginEntry), ``kernel/`` (PluginSpec auto-detect)
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

from lca.layer0_infra.plugin.loader._entry import PluginEntry


class ProfileError(RuntimeError):
    """Profile composition failure: missing file, bad YAML, import error."""


# ── YAML I/O ──────────────────────────────────────────────


def _read_yaml(path: Path) -> Any:
    try:
        with path.open() as f:
            return yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise ProfileError(f"profile file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ProfileError(f"profile YAML invalid: {path}: {exc}") from exc


def _write_yaml_atomic(path: Path, data: Any) -> None:
    """Atomic write: write .tmp then rename (mirrors Cordis Include._writeFile)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False))
    tmp.rename(path)


# ── Bundle expansion ──────────────────────────────────────


def compose_bundles(bundles: list[Path]) -> list[PluginEntry]:
    """Expand bundles: append each bundle's ``insert`` in order."""
    result: list[PluginEntry] = []
    for bundle in bundles:
        data = _read_yaml(bundle)
        if not isinstance(data, dict):
            raise ProfileError(f"bundle {bundle} is not a mapping")
        inserts = data.get("insert", [])
        if not isinstance(inserts, list):
            raise ProfileError(f"bundle {bundle} 'insert' is not a list")
        for row in inserts:
            if not isinstance(row, dict):
                raise ProfileError(f"bundle {bundle} insert row not a mapping")
            entry_id = row.get("id")
            if not entry_id or not isinstance(entry_id, str):
                raise ProfileError(f"bundle {bundle} insert row missing 'id'")
            result.append(
                PluginEntry(
                    id=entry_id,
                    module=None,
                    config=dict(row.get("config", {}) or {}),
                    disabled=bool(row.get("disabled", False)),
                    source=str(bundle),
                    plugin_name=row.get("name", ""),
                    inject=row.get("inject"),
                )
            )
    return result


# ── Patch application ─────────────────────────────────────


def _apply_patch(entries: list[PluginEntry], patch: list[dict[str, Any]]) -> list[PluginEntry]:
    """Apply patch: by-id config replacement (shallow) + insert."""
    result = list(entries)
    for row in patch:
        if not isinstance(row, dict):
            raise ProfileError(f"patch row not a mapping: {row}")

        if "insert" in row:
            inserts = row["insert"]
            if not isinstance(inserts, list):
                raise ProfileError("patch 'insert' is not a list")
            for new_row in inserts:
                if not isinstance(new_row, dict):
                    raise ProfileError("patch insert row not a mapping")
                entry_id = new_row.get("id")
                if not entry_id or not isinstance(entry_id, str):
                    raise ProfileError("patch insert row missing 'id'")
                result.append(
                    PluginEntry(
                        id=entry_id,
                        config=dict(new_row.get("config", {}) or {}),
                        disabled=bool(new_row.get("disabled", False)),
                        source="patch",
                        plugin_name=new_row.get("name", ""),
                        inject=new_row.get("inject"),
                    )
                )
            continue

        entry_id = row.get("id")
        if not entry_id:
            raise ProfileError(f"patch row missing 'id' or 'insert': {row}")

        found = False
        for i, e in enumerate(result):
            if e.id == entry_id:
                if "config" in row:
                    result[i] = PluginEntry(
                        id=e.id,
                        config=dict(row["config"] or {}),
                        disabled=bool(row.get("disabled", e.disabled)),
                        source=e.source,
                        plugin_name=e.plugin_name,
                        inject=row.get("inject", e.inject),
                    )
                elif "disabled" in row:
                    result[i] = PluginEntry(
                        id=e.id,
                        config=e.config,
                        disabled=bool(row["disabled"]),
                        source=e.source,
                        plugin_name=e.plugin_name,
                        inject=e.inject,
                    )
                found = True
                break

        if not found:
            import structlog

            structlog.get_logger("lca.profile").warning("patch_entry_not_found", entry_id=entry_id)
    return result


# ── Profile expansion ─────────────────────────────────────


def expand_profile(profile_path: Path) -> list[PluginEntry]:
    """Expand profile: bundles in order → apply patch."""
    data = _read_yaml(profile_path)
    if not isinstance(data, dict):
        raise ProfileError(f"profile {profile_path} is not a mapping")

    bundles = data.get("bundles", [])
    if not isinstance(bundles, list):
        raise ProfileError(f"profile {profile_path} 'bundles' not a list")

    bundle_paths = [Path(b) for b in bundles]
    entries = compose_bundles(bundle_paths)

    patch = data.get("patch", [])
    if patch:
        if not isinstance(patch, list):
            raise ProfileError(f"profile {profile_path} 'patch' not a list")
        entries = _apply_patch(entries, patch)

    return entries


# ── Module resolution ─────────────────────────────────────


def _resolve_module(name: str) -> Any:
    """Import plugin module by dotted path."""
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ProfileError(f"cannot import plugin module {name!r}: {exc}") from exc


class ProfileLoader:
    """Full pipeline: YAML → entries → resolved modules."""

    def load_profile(self, profile_path: Path) -> list[PluginEntry]:
        """Load and resolve all modules in a profile."""
        entries = expand_profile(profile_path)
        resolved: list[PluginEntry] = []
        for entry in entries:
            if entry.module is None:
                if not entry.plugin_name:
                    raise ProfileError(f"profile entry {entry.id!r} missing 'name'")
                module = _resolve_module(entry.plugin_name)
                entry = PluginEntry(
                    id=entry.id,
                    module=module,
                    config=entry.config,
                    disabled=entry.disabled,
                    source=entry.source,
                    plugin_name=entry.plugin_name,
                    inject=entry.inject,
                )
            resolved.append(entry)
        return resolved

    def dump_profile(self, profile_path: Path) -> list[dict[str, Any]]:
        """Dump expanded profile (id / name / config / source)."""
        entries = expand_profile(profile_path)
        return [
            {
                "id": e.id,
                "name": e.plugin_name,
                "config": e.config,
                "disabled": e.disabled,
                "source": e.source,
            }
            for e in entries
        ]
