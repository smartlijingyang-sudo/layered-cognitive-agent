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
        plugin_obj = getattr(module, entry.name)
        if hasattr(plugin_obj, "setup"):
            await plugin_obj.setup(ctx, entry.config)
    return ctx


def _resolve_module(entry: Entry) -> Any:
    """Resolve $module from YAML entry."""
    module_path = entry.extra.get("$module")
    if module_path is None:
        raise ValueError(f"entry {entry.id!r} missing $module")
    return importlib.import_module(module_path)
