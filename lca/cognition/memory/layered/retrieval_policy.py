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

from datetime import UTC, datetime

from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.protocols import RetrievalPolicy

_SEMANTIC_PROCEDURAL_BUDGET_RATIO = 0.7
_EPISODIC_BUDGET_RATIO = 0.3
_DEFAULT_RECENCY = 0.5
_DEFAULT_RELEVANCE = 1.0


def estimate_tokens(text: str) -> int:
    """字符级 token 近似（ADR-0246 PR-4）：约 4 字符 ≈ 1 token。"""
    return max(1, (len(text) + 3) // 4)


def _relevance(query: str, content: str) -> float:
    """查询词项与记忆内容的重叠度；无查询时返回中性值 1.0。

    中文按字符集合重叠，英文按词集合重叠。重叠度是简单的词项召回率，
    不是语义相似度——排序的语义部分由 recency×importance 承载。
    """
    if not query:
        return _DEFAULT_RELEVANCE
    q = query.lower().strip()
    c = content.lower()
    if not q:
        return 0.0
    if any("\u4e00" <= ch <= "\u9fff" for ch in q):
        q_set = set(q)
        c_set = set(c)
        return len(q_set & c_set) / len(q_set) if q_set else 0.0
    q_words = set(q.split())
    c_words = set(c.split())
    return len(q_words & c_words) / len(q_words) if q_words else 0.0


def _is_expired(record: MemoryRecord) -> bool:
    if record.valid_until_ms is None:
        return False
    return record.valid_until_ms < int(datetime.now(UTC).timestamp() * 1000)


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
        sp_kept = self._top_by_score(sp_pool, sp_budget, query=query)
        ep_pool = list(layers.get(MemoryLayer.EPISODIC, ()))
        ep_kept = self._top_by_score(ep_pool, ep_budget, query=query)

        selected = working + sp_kept + ep_kept
        return self._apply_token_budget(selected, token_budget=token_budget)

    @staticmethod
    def _top_by_score(
        records: list[MemoryRecord],
        budget: int,
        *,
        query: str,
    ) -> list[MemoryRecord]:
        """Stable top-``budget`` selection by ``relevance × recency × importance``。

        排除 superseded（``deleted=True``）与过期记录。无查询时退化为
        ``recency × importance`` 排序（确定性，同一输入两次结果一致）。
        """
        active = [r for r in records if not r.deleted and not _is_expired(r)]
        if budget <= 0 or not active:
            return []
        scored = sorted(
            active,
            key=lambda r: (
                _relevance(query, r.content)
                * (r.recency_score if r.recency_score is not None else _DEFAULT_RECENCY)
                * r.importance
            ),
            reverse=True,
        )
        return scored[:budget]

    @staticmethod
    def _apply_token_budget(
        records: list[MemoryRecord],
        *,
        token_budget: int | None,
    ) -> list[MemoryRecord]:
        """按字符级 token 估算截断；``token_budget=None`` 表示不截断。"""
        if token_budget is None or token_budget <= 0:
            return records
        kept: list[MemoryRecord] = []
        used = 0
        for record in records:
            estimated = estimate_tokens(record.content)
            if used + estimated > token_budget:
                break
            kept.append(record)
            used += estimated
        return kept


__all__ = ["LayeredRetrievalPolicy", "estimate_tokens"]
