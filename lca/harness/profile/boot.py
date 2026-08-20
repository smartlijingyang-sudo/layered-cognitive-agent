"""Boot a harness plugin tree from a profile YAML.

Returns a :class:`cordis.Context` with all plugins loaded. Thin wrapper
over :class:`cordis.loader.Loader`.

Profile YAML structure (LCA extension on top of cordis)::

  bundles:
    - bundles/base.yaml
    - bundles/web-app.yaml
  patch:
    - id: <plugin-id>      # override config (merged, not replaced)
      config: { ... }
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml
from cordis import Context


async def boot_profile(profile_path: Path | str) -> Context:
    """Load profile YAML → resolve modules → build root Context.

    Every entry is expected to use ``$module``; bare ``name`` resolution
    was a legacy escape hatch that no current bundle relies on.
    """
    path = Path(profile_path)
    raw = yaml.safe_load(path.read_text()) or {}  # noqa: ASYNC240 (boot is one-shot)

    # 1. Merge bundles
    all_entries: list[dict] = []
    for bundle_path in raw.get("bundles", []):
        bundle_full = Path(bundle_path)
        if not bundle_full.is_absolute():
            candidate = path.parent / bundle_path
            bundle_full = candidate if candidate.exists() else Path.cwd() / bundle_path
        bundle_data = yaml.safe_load(bundle_full.read_text()) or {}
        all_entries.extend(bundle_data.get("entries", []))

    # 2. Apply patches (merge into matching entry's config)
    patches = {p["id"]: p for p in raw.get("patch", []) if "id" in p}
    for entry in all_entries:
        if entry["id"] in patches:
            entry.setdefault("config", {}).update(patches[entry["id"]].get("config", {}))

    # 3. cordis.Loader parses; async-apply each entry
    tree = _load_from_dict({"entries": all_entries})
    ctx = Context()
    for entry in tree.entries:
        if entry.disabled or (isinstance(entry.config, dict) and entry.config.get("disabled")):
            continue
        module_path = entry.extra.get("$module")
        if not module_path:
            raise ValueError(
                f"bundle entry {entry.id!r} has no $module; bare-name resolution was removed"
            )
        module = importlib.import_module(module_path)
        # Skip entries whose module never declared a cordis ``setup``
        # (some gates live as plain dataclasses; they'll be wired by a
        # future plugin wrapper, not by boot itself).
        if not hasattr(module, "setup"):
            continue
        config = entry.config
        config_cls = getattr(module.setup, "Config", None) or getattr(module, "Config", None)
        if config_cls is not None and not isinstance(config, config_cls):
            config = config_cls.model_validate(config)
        await module.setup.setup(ctx, config)
    # Stash the resolved entry list on ctx so the boot report can walk it
    # without re-parsing YAML.
    ctx.__dict__["entries"] = list(tree.entries)
    return ctx


def _load_from_dict(data: dict) -> Any:
    """Build an EntryTree from a parsed dict (skip YAML re-parsing)."""
    from cordis import loader as _loader

    return _loader.Loader().load(data)
