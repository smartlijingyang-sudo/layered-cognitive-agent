"""TaskCoordinator —— 在多候选方案间做最终仲裁，产出唯一的 StructuredDecision。"""

from __future__ import annotations

from lca.contracts.state import TypedState
from lca.contracts.decision import StructuredDecision
from lca.contracts.protocols import TaskCoordinator


class SimpleTaskCoordinator(TaskCoordinator):
    """选择得分最高的候选方案。"""

    async def arbitrate(
        self, state: TypedState, candidates: list[StructuredDecision], scores: list[float]
    ) -> StructuredDecision:
        best_idx = max(range(len(candidates)), key=lambda i: scores[i])
        return candidates[best_idx]
