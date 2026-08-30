"""PluginGraphRenderer —— Coding Agent 只读 render Mermaid。"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.coding_agent_tools import PluginGraphRendererTool
from lca.plugins.tools.diagnostics._helpers import (
    _load_inspector_from_jsonl,
)


class PluginGraphRenderer(PluginGraphRendererTool):
    """只读 render plugin interaction graph。"""

    def __init__(self, jsonl_path: Path | str) -> None:
        self._path = Path(jsonl_path)

    def render(self, *, run_id: str) -> str:
        inspector = _load_inspector_from_jsonl(self._path)
        return inspector.plugin_interaction_graph()


__all__ = ["PluginGraphRenderer"]
