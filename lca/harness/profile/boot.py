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
    data = load_yaml(path)
    ctx = Context()
    loader = Loader()
    entries = loader.load(data)
    for entry in entries:
        module = _resolve_module(entry)
        # Try cordis @plugin style first (entry has its own setup() function)
        if hasattr(module, "setup"):
            await module.setup(ctx, entry.config)
            continue
        # Fallback: legacy LCA plugin (manifest + apply / mount)
        if hasattr(module, "apply"):
            from lca.plugins._compat import legacy_plugin_setup
            legacy_plugin_setup(ctx, entry.extra.get("$module", entry.name), entry.config)
            continue
        # Otherwise, the entry name itself is the plugin — use the compat shim
        from lca.plugins._compat import legacy_plugin_setup
        legacy_plugin_setup(ctx, entry.name, entry.config)
    return ctx


def _resolve_module(entry: Entry) -> Any:
    """Resolve $module from YAML entry."""
    module_path = entry.extra.get("$module")
    if module_path is None:
        raise ValueError(f"entry {entry.id!r} missing $module")
    return importlib.import_module(module_path)
