"""FailureExplainer —— Coding Agent 只读 explain_failure。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.contracts.observability.coding_agent_tools import FailureExplainerTool
from lca.infrastructure.observability.coding_agent_tools._helpers import (
    _load_inspector_from_jsonl,
    _serialize_report,
)


class FailureExplainer(FailureExplainerTool):
    """只读 explain_failure。"""

    def __init__(self, jsonl_path: Path | str) -> None:
        self._path = Path(jsonl_path)

    def explain_failure(self, *, run_id: str, depth: int = 24) -> dict[str, Any]:
        inspector = _load_inspector_from_jsonl(self._path)
        report = inspector.explain_failure(run_id=run_id, depth=depth)
        return _serialize_report(report)


__all__ = ["FailureExplainer"]
