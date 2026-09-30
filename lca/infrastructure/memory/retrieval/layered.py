"""LayeredRetrievalPolicy —— 4 层加权 retrieval（ADR-0068 / v3 §8 + ADR-0246 PR-4）。

策略：
- WORKING 永保留（不占 budget；Reflect 之前必须看到当前 turn 上下文）
- SEMANTIC + PROCEDURAL 按 ``relevance × recency × importance`` 排序，
  共享剩余 budget 的 70%
- EPISODIC 仅在 budget 剩余时填充，占 30%
- superseded（``deleted=True``）与过期（``valid_until_ms`` 已过）记录不参与
- ``token_budget`` 提供字符级 token 估算截断（ADR-0246 §3.3）

researcher profile 装此实现取代 NullRetrievalPolicy。
"""

from __future__ import annotations

from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.protocols import RetrievalPolicy
from lca.infrastructure.memory.retrieval.scoring import apply_token_budget, select_top

_SEMANTIC_PROCEDURAL_BUDGET_RATIO = 0.7
_EPISODIC_BUDGET_RATIO = 0.3


class LayeredRetrievalPolicy(RetrievalPolicy):
    """Per-layer weighted retrieval across 4 memory layers (ADR-0068 + ADR-0246)."""

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
        *,
        query: str = "",
        token_budget: int | None = None,
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
        sp_kept = select_top(sp_pool, sp_budget, query=query)
        ep_pool = list(layers.get(MemoryLayer.EPISODIC, ()))
        ep_kept = select_top(ep_pool, ep_budget, query=query)

        selected = working + sp_kept + ep_kept
        return apply_token_budget(selected, token_budget=token_budget)


__all__ = ["LayeredRetrievalPolicy"]
