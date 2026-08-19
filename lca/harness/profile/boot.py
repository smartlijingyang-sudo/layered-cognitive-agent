"""Boot a harness plugin tree from a profile YAML.

Returns a cordis.Context with all plugins loaded. Thin wrapper around
cordis.Loader.
"""
from __future__ import annotations

import importlib
import warnings
from pathlib import Path
from typing import Any

from cordis import Context
from cordis.loader import Entry, Loader, load_yaml


async def boot_profile(
    profile_path: Path | str,
    *,
    check_seam_completeness: bool = True,
) -> Context:
    """Load profile YAML → resolve modules → build root Context.

    Profile YAML structure:
      bundles:
        - bundles/base.yaml
        - bundles/web-app.yaml
      patch:
        - id: <plugin-id>
          config: { ... }
    """
    if check_seam_completeness:
        warnings.warn(
            "check_seam_completeness is deprecated; cordis doesn't validate seams",
            DeprecationWarning,
            stacklevel=2,
        )

    path = Path(profile_path)
    tree = load_yaml(path)
    ctx = Context()
    # Walk the EntryTree directly (Loader.load() re-parses, but we already have a tree)
    from lca.plugins._compat import legacy_plugin_setup
    for entry in tree.entries:
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
            await module.setup.setup(ctx, entry.config)
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
