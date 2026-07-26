"""StatePredictor —— 预测候选行动执行后的状态变化。"""

from __future__ import annotations

from typing import Any

from contracts.state import TypedState


class SimpleStatePredictor:
    """最小实现：直接以候选动作描述作为预期效果。"""

    async def predict(self, state: TypedState, candidate_action: str) -> dict[str, Any]:
        return {"expected_effect": candidate_action}
