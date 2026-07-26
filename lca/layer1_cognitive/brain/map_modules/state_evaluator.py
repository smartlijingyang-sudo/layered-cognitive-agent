"""StateEvaluator —— 对候选行动/预测结果打分。"""

from __future__ import annotations

from typing import Any

from lca.contracts.state import TypedState
from lca.contracts.protocols import StateEvaluator


class SimpleStateEvaluator(StateEvaluator):
    """单候选场景：评分仅用于保持 MAP 协作链路完整。"""

    async def score(self, state: TypedState, predicted_state: dict[str, Any]) -> float:
        return 1.0
