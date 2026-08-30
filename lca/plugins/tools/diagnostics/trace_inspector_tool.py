"""TraceInspectorTool 实现 —— Coding Agent 只读 inspect_trace。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.contracts.observability.coding_agent_tools import TraceInspectorTool
from lca.plugins.tools.diagnostics._helpers import (
    _load_inspector_from_jsonl,
    _serialize_report,
)


class TraceInspectorToolAdapter(TraceInspectorTool):
    """只读 inspect_trace;读 journal.jsonl + TraceInspector 派生。"""

    def __init__(self, jsonl_path: Path | str) -> None:
        self._path = Path(jsonl_path)

    def inspect_trace(
        self,
        *,
        run_id: str,
        focus: str = "all",
        depth: int = 24,
    ) -> dict[str, Any]:
        inspector = _load_inspector_from_jsonl(self._path)
        report = inspector.inspect_trace(run_id=run_id, focus=focus, depth=depth)
        return _serialize_report(report)


__all__ = ["TraceInspectorToolAdapter"]
