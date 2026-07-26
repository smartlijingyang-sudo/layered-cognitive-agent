"""ConflictMonitor —— 检测目标冲突、资源冲突、决策不一致。"""

from __future__ import annotations

from lca.contracts.state import TypedState
from lca.contracts.decision import StructuredDecision
from lca.contracts.protocols import ConflictMonitor


class SimpleConflictMonitor(ConflictMonitor):
    """最小实现：不检测冲突。"""

    async def check(self, state: TypedState, candidates: list[StructuredDecision]) -> list[str]:
        return []
