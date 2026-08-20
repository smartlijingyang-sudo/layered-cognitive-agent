"""Boot a harness plugin tree from a profile YAML.

Returns a cordis.Context with all plugins loaded. Thin wrapper around
cordis.Loader.

Profile YAML structure (LCA extension on top of cordis):
  bundles:
    - bundles/base.yaml
    - bundles/web-app.yaml
  patch:
    - id: <plugin-id>      # override config
      config: { ... }
"""
from __future__ import annotations

import importlib
import warnings
from pathlib import Path
from typing import Any

import yaml
from cordis import Context


async def boot_profile(
    profile_path: Path | str,
    *,
    check_seam_completeness: bool = True,
) -> Context:
    """Load profile YAML → resolve modules → build root Context."""
    if check_seam_completeness:
        warnings.warn(
            "check_seam_completeness is deprecated; cordis doesn't validate seams",
            DeprecationWarning,
            stacklevel=2,
        )

    path = Path(profile_path)
    raw = yaml.safe_load(path.read_text()) or {}

    # Merge bundles (LCA extension: load each bundle YAML, concat entries)
    all_entries: list[dict] = []
    for bundle_path in raw.get("bundles", []):
        bundle_full = Path(bundle_path)
        if not bundle_full.is_absolute():
            # Profile paths like "bundles/base.yaml" — try relative to profile dir first,
            # then to cwd.
            candidate = path.parent / bundle_path
            if candidate.exists():
                bundle_full = candidate
            else:
                bundle_full = Path.cwd() / bundle_path
        bundle_data = yaml.safe_load(bundle_full.read_text()) or {}
        all_entries.extend(bundle_data.get("entries", []))

    # Apply patches (LCA extension: override config for matching ids)
    patches = {p["id"]: p for p in raw.get("patch", []) if "id" in p}
    for entry in all_entries:
        if entry["id"] in patches:
            entry.setdefault("config", {}).update(patches[entry["id"]].get("config", {}))

    # Build a merged YAML doc and load via cordis
    merged = {"entries": all_entries}
    tree = _load_from_dict(merged)
    ctx = Context()
    from lca.plugins._compat import legacy_plugin_setup
    for entry in tree.entries:
        # ``disabled: true`` in config skips the plugin's setup.
        if entry.disabled or (
            isinstance(entry.config, dict) and entry.config.get("disabled")
        ):
            continue
        # cordis @plugin decorator wraps the function in a Plugin dataclass
        # (with `setup` as a field). To call, we need module.setup.setup(ctx, config).
        module_path = entry.extra.get("$module")
        if module_path is None:
            # Try legacy entry — name maps to plugin module
            module = _resolve_module_by_name(entry.name)
        else:
            module = _resolve_module_by_path(module_path)
        # Try cordis @plugin style first (Plugin dataclass with .setup field)
        if hasattr(module, "setup") and hasattr(module.setup, "setup"):
            # cordis Plugin has a Config field. Look up the plugin's Config
            # class either from the Plugin dataclass (if explicitly set via
            # `@plugin(Config=...)`) or from the module's globals (by name).
            config = entry.config
            config_cls = getattr(module.setup, "Config", None)
            if config_cls is None:
                # Convention: each plugin file has a `Config` Pydantic class.
                config_cls = getattr(module, "Config", None)
            if config_cls is not None and not isinstance(config, config_cls):
                config = config_cls.model_validate(config)
            await module.setup.setup(ctx, config)
            continue
        # Fallback: legacy LCA plugin (manifest + apply)
        if hasattr(module, "apply"):
            legacy_plugin_setup(ctx, module_path or entry.name, entry.config)
            continue
    return ctx


def _resolve_module_by_name(name: str) -> Any:
    """Resolve plugin module by name (for legacy entries)."""
    return importlib.import_module(name)


def _resolve_module_by_path(path: str) -> Any:
    """Resolve plugin module by path."""
    return importlib.import_module(path)


def _load_from_dict(data: dict) -> Any:
    """Build an EntryTree from a parsed dict (skips YAML re-parsing)."""
    # Lazy import to avoid circular dependency
    from cordis import loader as _loader
    return _loader.Loader().load(data)
