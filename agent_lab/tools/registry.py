"""Compat shim — agent_lab.tools.registry was deleted in PR-E.2.

This stub exists only so the legacy ``agent_lab.nodes.act.execute.body``
shim (which is itself slated for PR-D final deletion) can still
import ``ToolRegistry`` and ``LabToolRegistry``. Both classes return
empty registries because the YAML inventory is now driven by the
LCA plugin layer (see ``lca.plugins.lab.tools.provider``).

delete-when (PR-D final):
- agent_lab/nodes/act/execute/body.py replaced by body composition in
  lca.plugins.lab.act.compose (PR-E; previously lca.plugins.lab.act.body_provider);
  this shim then becomes dead code.
- agent_lab/nodes/act/execute/plugin.py replaced by @plugin carrier in
  lca.plugins.lab.act.execute; body.py becomes unreachable.
"""

from __future__ import annotations

from typing import Any


class ToolRegistry:
    """Empty compat shim. The agent_lab tool inventory lives in
    ``lca.plugins.lab.tools.provider`` (PR-D final)."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}

    def load_from_yaml(self, path) -> None:
        """No-op; tools are loaded by lca.plugins.lab.tools.provider."""
        return None

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def contains(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> Any | None:
        return self._tools.get(name)

    def register(self, name: str, tool: Any) -> None:
        self._tools[name] = tool


# Backwards-compat alias the deleted registry exposed.
LabToolRegistry = ToolRegistry


class ToolNotFoundError(KeyError):
    pass


__all__ = ["ToolRegistry", "LabToolRegistry", "ToolNotFoundError"]
