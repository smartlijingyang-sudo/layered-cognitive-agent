"""LayeredRetrievalPolicy —— 4 层加权 retrieval（ADR-0068 / v3 §8）。

策略：
- WORKING 永保留（不占 budget；Reflect 之前必须看到当前 turn 上下文）
- SEMANTIC + PROCEDURAL 按 ``recency_score`` 排序，共享剩余 budget 的 70%
- EPISODIC 仅在 budget 剩余时填充，占 30%

researcher profile 装此实现取代 NullRetrievalPolicy。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.protocols import RetrievalPolicy

_SEMANTIC_PROCEDURAL_BUDGET_RATIO = 0.7
_EPISODIC_BUDGET_RATIO = 0.3


class LayeredRetrievalPolicy(RetrievalPolicy):
    """Per-layer weighted retrieval across 4 memory layers (ADR-0068)."""

    def __init__(
        self,
        *,
        semantic_procedural_budget_ratio: float = _SEMANTIC_PROCEDURAL_BUDGET_RATIO,
        episodic_budget_ratio: float = _EPISODIC_BUDGET_RATIO,
    ) -> None:
        self._sp_ratio = semantic_procedural_budget_ratio
        self._ep_ratio = episodic_budget_ratio

    def retrieve(
        self,
        layers: dict[MemoryLayer, list[MemoryRecord]],
        budget: int,
    ) -> list[MemoryRecord]:
        if budget <= 0:
            return []
        working = list(layers.get(MemoryLayer.WORKING, ()))
        # Working is preserved unconditionally and does not consume budget.
        remaining = max(0, budget - len(working))
        if remaining <= 0:
            return working[:budget]

        sp_budget = int(remaining * self._sp_ratio)
        ep_budget = remaining - sp_budget

        sp_pool = list(layers.get(MemoryLayer.SEMANTIC, ())) + list(
            layers.get(MemoryLayer.PROCEDURAL, ())
        )
        sp_kept = self._top_by_recency(sp_pool, sp_budget)
        ep_pool = list(layers.get(MemoryLayer.EPISODIC, ()))
        ep_kept = self._top_by_recency(ep_pool, ep_budget)

        return working + sp_kept + ep_kept

    @staticmethod
    def _top_by_recency(records: list[MemoryRecord], budget: int) -> list[MemoryRecord]:
        """Stable top-``budget`` selection by ``recency_score`` (descending).

        Records with ``recency_score is None`` sort as 0.0.
        When ``records`` fits in ``budget`` the input order is preserved.
        """
        if budget <= 0 or not records:
            return []
        if len(records) <= budget:
            return list(records)
        scored = sorted(
            records,
            key=lambda r: (
                r.recency_score is not None,
                r.recency_score if r.recency_score is not None else 0.0,
            ),
            reverse=True,
        )
        kept = scored[:budget]
        kept_ids = {r.record_id for r in kept}
        return [r for r in records if r.record_id in kept_ids]


__all__ = ["LayeredRetrievalPolicy"]
