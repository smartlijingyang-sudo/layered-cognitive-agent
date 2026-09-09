# PR-D final — tool registry provider real composition
"""lab.tool_registry provider — load tools from inventory and expose a
lab-shaped registry.

Replaces the PR-B marker + the deleted ``agent_lab/tools/registry.yaml`` path.
On first access, lazy-loads from ``_INVENTORY`` (inline);``configure(path)``
overrides with a YAML file if provided.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Inline inventory —— 默认工具集,够 act 端到端 demo。
# plan scope:act 工人 import 这些 tool 类实现;yaml 是历史层,删。
# ---------------------------------------------------------------------------
_INVENTORY: tuple[tuple[str, str], ...] = (
    # (name, "module:Factory")
    ("bash", "lca.plugins.lab.tools.implementations.bash:BashTool"),
    ("file_write", "lca.plugins.lab.tools.implementations.file_write:FileWriteTool"),
    ("read_file", "lca.plugins.lab.tools.implementations.read_file:ReadFileTool"),
)


_LAB_TOOLS: dict[str, Any] = {}
_TOOL_YAML: Path | None = None


def configure(yaml_path):
    """Boot: 加载 yaml 工具清单;缺文件时退化为 inline inventory。"""
    global _TOOL_YAML
    p = Path(yaml_path) if isinstance(yaml_path, str) else yaml_path
    _TOOL_YAML = p
    _LAB_TOOLS.clear()
    if p.exists():
        _load_yaml(p)
    else:
        _load_inventory()


def _load_yaml(path):
    """Parse the lab tool inventory YAML and instantiate each entry."""
    import yaml

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    for entry in data.get("tools", []):
        ref = entry.get("ref")
        if not ref or ":" not in ref:
            continue
        _instantiate(entry.get("name") or ref.split(":", 1)[1], ref)


def _load_inventory():
    """Load inline inventory (default tool set)."""
    for name, ref in _INVENTORY:
        _instantiate(name, ref)


def _instantiate(name: str, ref: str) -> None:
    if ":" not in ref:
        return
    mod_name, attr = ref.split(":", 1)
    try:
        mod = importlib.import_module(mod_name)
        factory = getattr(mod, attr, None)
        if factory is None:
            return
        tool = factory() if callable(factory) else factory
        _LAB_TOOLS[name] = tool
    except Exception:  # pragma: no cover - import failures
        pass


class _Registry:
    """Plain object exposing dict-like access + ``.names()`` for old consumers."""

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = dict(mapping)

    def __getitem__(self, name: str) -> Any:
        return self._mapping[name]

    def __contains__(self, name: str) -> bool:
        return name in self._mapping

    def __iter__(self):
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def get(self, name: str, default: Any = None) -> Any:
        return self._mapping.get(name, default)

    def names(self) -> list[str]:
        return sorted(self._mapping.keys())

    def values(self):
        return self._mapping.values()

    def items(self):
        return self._mapping.items()


def get_registry():
    """Return the live registry(支持 ``.names()`` + dict-like access)。"""
    if not _LAB_TOOLS:
        _load_inventory()
    return _Registry(_LAB_TOOLS)


def names():
    return get_registry().names()


def contains(name):
    return name in get_registry()


__all__ = ["configure", "get_registry", "names", "contains"]
from lca.plugins.lab.internal.loader import _LAB_HOOKS
_LAB_HOOKS["lab.tools.provider"] = {"id": "provider", "stage": "composition"}