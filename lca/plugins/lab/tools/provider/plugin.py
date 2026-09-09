# PR-D final — tool registry provider real composition
"""lab.tool_registry provider — load tools/registry.yaml and expose a
lab-shaped registry.

Replaces the PR-B marker. Reads the same YAML format that the deleted
agent_lab/tools/registry.yaml used (one entry per line: ``- ref: module:Factory``)
so the existing tools/implementations/* classes can be loaded without
touching the consumer code that used the old LabToolRegistry.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_LAB_TOOLS: dict[str, Any] = {}
_TOOL_YAML: Path | None = None


def configure(yaml_path):
    """Boot: point at the lab tool inventory YAML.

    Called from agent_lab.run once at process startup; idempotent.
    """
    global _TOOL_YAML
    p = Path(yaml_path) if isinstance(yaml_path, str) else yaml_path
    _TOOL_YAML = p
    _LAB_TOOLS.clear()
    _load_yaml(p)


def _load_yaml(path):
    """Parse the lab tool inventory YAML and instantiate each entry."""
    import yaml

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    for entry in data.get("tools", []):
        ref = entry.get("ref")
        if not ref or ":" not in ref:
            continue
        mod_name, attr = ref.split(":", 1)
        try:
            mod = importlib.import_module(mod_name)
            factory = getattr(mod, attr, None)
            if factory is None:
                continue
            tool = factory() if callable(factory) else factory
            name = entry.get("name") or attr
            _LAB_TOOLS[name] = tool
        except Exception:  # pragma: no cover - import failures
            pass


def get_registry():
    """Return the live {name: tool} map.

    Lazy-loads the YAML on first access if configure() was not called.
    """
    if not _LAB_TOOLS and _TOOL_YAML is None:
        configure(_default_yaml_path())
    return dict(_LAB_TOOLS)


def names():
    return sorted(_LAB_TOOLS.keys())


def contains(name):
    return name in _LAB_TOOLS


def _default_yaml_path():
    return Path(__file__).resolve().parents[4] / "agent_lab" / "tools" / "tools.yaml"


__all__ = ["configure", "get_registry", "names", "contains"]

# Register loader marker for the capability closure.
from lca.plugins.lab.internal.loader import _LAB_HOOKS
_LAB_HOOKS["lab.tools.provider"] = {"id": "provider", "stage": "composition"}