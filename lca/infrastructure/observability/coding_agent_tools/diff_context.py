"""DiffContext —— Coding Agent 只读 diff(同 run 不同 step context)。"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.coding_agent_tools import ContextDiff, DiffContextTool
from lca.infrastructure.observability.coding_agent_tools._helpers import (
    _inspector_events,
    _load_inspector_from_jsonl,
)


class DiffContext(DiffContextTool):
    """只读 diff(skeleton):返回 step 之间的 item_added / removed 推导。

    实际实现里这一步依赖 ContextManifest 重建;此处给最小骨架,
    diff items 返回空 tuple(详细实现留给 0065 后续 PR)。
    """

    def __init__(self, jsonl_path: Path | str) -> None:
        self._path = Path(jsonl_path)

    def diff(self, *, run_id: str, step: int = 0) -> ContextDiff:
        inspector = _load_inspector_from_jsonl(self._path)
        events = _inspector_events(inspector)
        events = [e for e in events if str(e.scope.run_id) == run_id]
        steps = sorted({e.scope.step for e in events})
        if not steps or step not in steps:
            return ContextDiff(run_id=run_id, step_a=step, step_b=step)
        idx = steps.index(step)
        if idx + 1 >= len(steps):
            return ContextDiff(run_id=run_id, step_a=step, step_b=step)
        next_step = steps[idx + 1]
        # 简化:返回骨架 diff,真实差异待后续 PR 用 ContextManifest 重建
        return ContextDiff(
            run_id=run_id,
            step_a=step,
            step_b=next_step,
            items_added=(),
            items_removed=(),
        )


__all__ = ["DiffContext"]
