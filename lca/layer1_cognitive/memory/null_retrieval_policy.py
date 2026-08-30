"""NullRetrievalPolicy —— 宪法 §3.4 默认 no-op（ADR-0068）。

``NullRetrievalPolicy.retrieve`` 始终返回 ``[]``。Profile 不挂
standard-memory bundle 时默认装载此实现；``SimpleMemorySystem.perceive``
把空列表写到 ``state.retrieved_context``，意味着 Reasoner 看不到任何
记忆记录。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.protocols import RetrievalPolicy


class NullRetrievalPolicy(RetrievalPolicy):
    """Default null RetrievalPolicy (ADR-0068 / 宪法 §3.4)."""

    def retrieve(
        self,
        layers: dict[MemoryLayer, list[MemoryRecord]],
        budget: int,
    ) -> list[MemoryRecord]:
        return []


__all__ = ["NullRetrievalPolicy"]
