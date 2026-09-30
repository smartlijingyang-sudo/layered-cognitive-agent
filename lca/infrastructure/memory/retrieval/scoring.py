"""Shared memory retrieval scoring (ADR-0068 / ADR-0246 PR-4).

Pure scoring algebra used by every memory retrieval path:
``LayeredRetrievalPolicy`` (per-layer weighted retrieval) and
``AssistantMemory.retrieve`` (single-pool semantic + episodic ranking).

The module lives in infrastructure so cognition policies and infrastructure
stores can depend on the same seam without upward imports: cognition imports
down, infrastructure imports its sibling, and ``contracts`` keeps only the
``RetrievalPolicy`` protocol. This removes the previous duplication where
``AssistantMemory`` reached into ``lca.cognition.memory.layered`` internals.
"""

from __future__ import annotations

from lca.contracts.atoms.ids.ids import utc_now_ms
from lca.contracts.models.core.conversation.memory import MemoryRecord

_DEFAULT_RECENCY = 0.5
_DEFAULT_RELEVANCE = 1.0


def estimate_tokens(text: str) -> int:
    """字符级 token 近似（ADR-0246 PR-4）：约 4 字符 ≈ 1 token。"""
    return max(1, (len(text) + 3) // 4)


def relevance(query: str, content: str) -> float:
    """查询词项与记忆内容的重叠度；无查询时返回中性值 1.0。

    中文按字符集合重叠，英文按词集合重叠。重叠度结合词项召回率与确切词项命中加成。
    """
    if not query:
        return _DEFAULT_RELEVANCE
    q = query.lower().strip()
    c = content.lower()
    if not q:
        return 0.0
    terms = [t for t in q.split() if len(t) >= 2]
    substring_bonus = 0.5 if (q in c or any(term in c for term in terms)) else 0.0
    if any("\u4e00" <= ch <= "\u9fff" for ch in q):
        q_set = set(q)
        c_set = set(c)
        overlap = len(q_set & c_set) / len(q_set) if q_set else 0.0
        return min(2.0, overlap + substring_bonus)
    q_words = set(q.split())
    c_words = set(c.split())
    overlap = len(q_words & c_words) / len(q_words) if q_words else 0.0
    return min(2.0, overlap + substring_bonus)


def is_expired(record: MemoryRecord, *, now_ms: int | None = None) -> bool:
    """``valid_until_ms`` 已过则视为过期；无有效期则永不过期。"""
    if record.valid_until_ms is None:
        return False
    now = now_ms if now_ms is not None else utc_now_ms()
    return record.valid_until_ms < now


def score_record(
    record: MemoryRecord,
    query: str,
    *,
    now_ms: int | None = None,
) -> float:
    """ADR-0246 排序公式：``relevance × recency × importance``。

    ``recency_score`` 优先；未设置时若提供 ``now_ms`` 且记录有
    ``created_at_ms``，按指数衰减估算时效（``AssistantMemory`` 路径）；
    否则退化为中性值。``now_ms`` 由调用方注入以保持确定性测试。
    """
    rel = relevance(query, record.content)
    if record.recency_score is not None:
        rec = record.recency_score
    elif now_ms is not None and record.created_at_ms is not None and record.created_at_ms > 0:
        age_hours = max(0.0, (now_ms - record.created_at_ms) / (1000.0 * 3600.0))
        rec = max(0.2, 1.0 / (1.0 + age_hours * 0.05))
    else:
        rec = _DEFAULT_RECENCY
    imp = record.importance if record.importance is not None else _DEFAULT_RECENCY
    return rel * rec * imp


def select_top(
    records: list[MemoryRecord],
    budget: int,
    *,
    query: str = "",
    now_ms: int | None = None,
) -> list[MemoryRecord]:
    """Stable top-``budget`` selection by ``relevance × recency × importance``。

    排除 superseded（``deleted=True``）与过期记录。无查询时退化为
    ``recency × importance`` 排序（确定性，同一输入两次结果一致）。
    """
    active = [r for r in records if not r.deleted and not is_expired(r, now_ms=now_ms)]
    if budget <= 0 or not active:
        return []
    scored = sorted(
        active,
        key=lambda r: score_record(r, query, now_ms=now_ms),
        reverse=True,
    )
    return scored[:budget]


def apply_token_budget(
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


__all__ = [
    "apply_token_budget",
    "estimate_tokens",
    "is_expired",
    "relevance",
    "score_record",
    "select_top",
]
