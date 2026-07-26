"""ConflictMonitor —— 检测目标冲突、资源冲突、决策不一致。"""

from __future__ import annotations

from contracts.state import TypedState
from contracts.decision import StructuredDecision


class SimpleConflictMonitor:
    """最小实现：不检测冲突。"""

    async def check(self, state: TypedState, candidates: list[StructuredDecision]) -> list[str]:
        return []
