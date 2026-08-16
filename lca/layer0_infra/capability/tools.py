"""tools seam Definition — owns ctx.tools."""

from __future__ import annotations

from lca.contracts.protocols import Tool, ToolRegistry
from lca.layer0_infra.component_registry import NamedRegistry


class ToolsService(NamedRegistry[Tool], ToolRegistry):
    """Service Definition：工具注册表。每个 Tool 实现是 Provider。"""

    _REGISTRY_KIND = "tool"

    def register(self, tool: Tool) -> None:  # type: ignore[override]
        self._entries[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._entries.get(name)
