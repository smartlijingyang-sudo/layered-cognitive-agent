"""TaskDecomposer —— 将目标拆解为可执行子任务。"""

from __future__ import annotations

from contracts.state import TypedState
from contracts.protocols import TaskDecomposer


class SimpleTaskDecomposer(TaskDecomposer):
    """单步问答场景：无需真正拆解，直接返回原始任务。"""

    async def decompose(self, state: TypedState) -> list[str]:
        return [state.task]
