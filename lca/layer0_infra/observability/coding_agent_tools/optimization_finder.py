"""OptimizationFinder —— Coding Agent 只读 find_optimization_candidates。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.contracts.observability.coding_agent_tools import OptimizationFinderTool
from lca.layer0_infra.observability.coding_agent_tools._helpers import (
    _load_inspector_from_jsonl,
)


class OptimizationFinder(OptimizationFinderTool):
    """只读 optimization 排序(LLM/工具/Plugin 按 latency_ms 排序)。"""

    def __init__(self, jsonl_path: Path | str) -> None:
        self._path = Path(jsonl_path)

    def find_optimization_candidates(self, *, run_id: str, limit: int = 5) -> list[dict[str, Any]]:
        inspector = _load_inspector_from_jsonl(self._path)
        return list(inspector.find_optimization_candidates(limit=limit))


__all__ = ["OptimizationFinder"]
