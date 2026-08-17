"""Profile composition — YAML bundle expansion + patch + module resolution.

Mirrors DSH ``vendor/include/``:
- Read profile YAML → extract bundle list + patch list
- Expand bundles: append each bundle's ``insert`` entries in order
- Apply patch: by-id whole-config replacement + insert new entries
- Support group entries (``group: true``) whose ``config`` holds child rows
- Support ``!py`` expressions in config (Cordis ``!!js`` mirror)
- Resolve modules: import ``name`` paths → resolved ``module`` objects

Depends on: ``loader/`` (PluginEntry), ``kernel/`` (PluginSpec auto-detect)
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

# Registers the ``!py`` YAML tag constructor (import side effect).
import lca.layer0_infra.plugin.expr.pyexpr  # noqa: F401
from lca.layer0_infra.plugin.expr.pyexpr import interpolate
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


def _resolve_expr(value: Any, scope: dict[str, Any] | None = None) -> Any:
    """Resolve ``PyExpr`` nodes recursively against *scope* (default empty)."""
    return interpolate(value, scope or {})


def _row_to_entry(row: dict[str, Any], source: str) -> PluginEntry:
    """Convert one raw YAML row into a PluginEntry (recursing groups).

    ``cordis:`` prefixed names are builtin markers (groups, echo, etc.) and
    are never imported.
    """
    entry_id = row.get("id")
    if not entry_id or not isinstance(entry_id, str):
        raise ProfileError(f"insert row missing 'id': {row}")
    config = _resolve_expr(row.get("config", {}) or {})
    if isinstance(config, list):
        children = [_row_to_entry(c, source) for c in config]
        return PluginEntry(
            id=entry_id,
            module=None,
            config=children,
            disabled=bool(row.get("disabled", False)),
            source=source,
            plugin_name=row.get("name", ""),
            inject=row.get("inject"),
            group=bool(row.get("group", False)),
            isolate=row.get("isolate"),
        )
    return PluginEntry(
        id=entry_id,
        module=None,
        config=dict(config) if isinstance(config, dict) else {},
        disabled=bool(row.get("disabled", False)),
        source=source,
        plugin_name=row.get("name", ""),
        inject=row.get("inject"),
        group=bool(row.get("group", False)),
        isolate=row.get("isolate"),
    )


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
            result.append(_row_to_entry(row, str(bundle)))
    return result


# ── Patch application ─────────────────────────────────────


def _apply_patch(entries: list[PluginEntry], patch: list[dict[str, Any]]) -> list[PluginEntry]:
    """Apply patch: by-id whole-config replacement + insert (Cordis mirror).

    Patch semantics (DSH ``applyEntryPatches``):
    - ``insert`` without ``id`` appends to root; with ``id`` targets a group.
    - ``id`` present: whole-value override of ``config`` / ``disabled`` /
      ``inject`` — never a deep merge.
    - A patch matching nothing warns and is skipped.
    - Inserted rows are indexed immediately so a later patch can target them.
    """
    result = list(entries)
    index: dict[str, PluginEntry] = {}

    def _index_entry(e: PluginEntry) -> None:
        index[e.id] = e
        if e.group and isinstance(e.config, list):
            for child in e.config:
                _index_entry(child)

    for e in result:
        _index_entry(e)

    import structlog

    log = structlog.get_logger("lca.profile")

    for row in patch:
        if not isinstance(row, dict):
            raise ProfileError(f"patch row not a mapping: {row}")

        if "insert" in row:
            inserts = row["insert"]
            if not isinstance(inserts, list):
                raise ProfileError("patch 'insert' is not a list")
            parent_id = row.get("id")
            if parent_id is not None:
                target = index.get(parent_id)
                if target is None:
                    log.warning("patch_insert_target_missing", target=parent_id)
                    continue
                if not target.group or not isinstance(target.config, list):
                    log.warning("patch_insert_target_not_group", target=parent_id)
                    continue
                children = [_row_to_entry(c, "patch") for c in inserts]
                target.config.extend(children)
                for child in children:
                    _index_entry(child)
            else:
                new_rows = [_row_to_entry(r, "patch") for r in inserts]
                result.extend(new_rows)
                for new_row in new_rows:
                    _index_entry(new_row)
            continue

        entry_id = row.get("id")
        if not entry_id:
            log.warning("patch_row_missing_id", row=row)
            continue

        target = index.get(entry_id)
        if target is None:
            log.warning("patch_entry_not_found", entry_id=entry_id)
            continue

        patch_name = row.get("name")
        if patch_name and patch_name != target.plugin_name:
            log.warning(
                "patch_name_mismatch",
                entry_id=entry_id,
                expected=target.plugin_name,
                got=patch_name,
            )
            continue

        for key in ("config", "disabled", "inject", "group", "isolate"):
            if key in row:
                value = _resolve_expr(row[key])
                if key == "config" and isinstance(value, list):
                    target.config = [_row_to_entry(c, "patch") for c in value]
                elif key == "config":
                    target.config = dict(value) if isinstance(value, dict) else {}
                elif key == "disabled":
                    target.disabled = bool(value)
                elif key == "inject":
                    target.inject = value
                elif key == "group":
                    target.group = bool(value)
                elif key == "isolate":
                    target.isolate = value
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


def _resolve_entry_module(entry: PluginEntry) -> PluginEntry:
    """Import *entry's* module, recursing into groups.

    ``cordis:`` prefixed names resolve to builtin markers, never imported.
    """
    if entry.module is not None:
        return entry
    if entry.plugin_name and not entry.plugin_name.startswith("cordis:"):
        module = _resolve_module(entry.plugin_name)
        entry.module = module
    if entry.group and isinstance(entry.config, list):
        for child in entry.config:
            _resolve_entry_module(child)
    return entry


class ProfileLoader:
    """Full pipeline: YAML → entries → resolved modules."""

    def load_profile(self, profile_path: Path) -> list[PluginEntry]:
        """Load and resolve all modules in a profile."""
        entries = expand_profile(profile_path)
        return [_resolve_entry_module(e) for e in entries]

    def dump_profile(self, profile_path: Path) -> list[dict[str, Any]]:
        """Dump expanded profile (id / name / config / source)."""
        entries = expand_profile(profile_path)
        rows: list[dict[str, Any]] = []
        for e in entries:
            rows.append(
                {
                    "id": e.id,
                    "name": e.plugin_name,
                    "config": e.config,
                    "disabled": e.disabled,
                    "source": e.source,
                    "group": e.group,
                }
            )
            if e.group and isinstance(e.config, list):
                for child in e.config:
                    rows.append(
                        {
                            "id": child.id,
                            "name": child.plugin_name,
                            "config": child.config,
                            "disabled": child.disabled,
                            "source": child.source,
                            "parent": e.id,
                        }
                    )
        return rows
