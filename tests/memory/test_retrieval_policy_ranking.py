"""PR-4（ADR-0246）：检索策略排序确定性与相关性测试。"""

from __future__ import annotations

from lca.cognition.memory.layered.retrieval_policy import LayeredRetrievalPolicy
from lca.contracts.atoms.enums.enums import MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord


def _rec(
    record_id: str,
    content: str,
    *,
    importance: float,
    recency: float,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=importance,
        recency_score=recency,
    )


def _layers(records: list[MemoryRecord]) -> dict[MemoryLayer, list[MemoryRecord]]:
    return {MemoryLayer.SEMANTIC: records}


def test_ranking_is_deterministic() -> None:
    records = [
        _rec("a", "架构师身份", importance=0.9, recency=0.8),
        _rec("b", "偏好简洁", importance=0.7, recency=0.9),
        _rec("c", "一般事实", importance=0.5, recency=0.6),
    ]
    policy = LayeredRetrievalPolicy()
    layers = _layers(records)
    first = [r.record_id for r in policy.retrieve(layers, budget=10)]
    second = [r.record_id for r in policy.retrieve(layers, budget=10)]
    assert first == second


def test_ranking_orders_by_recency_times_importance() -> None:
    records = [
        _rec("high_imp_low_rec", "重要但旧", importance=0.9, recency=0.2),
        _rec("low_imp_high_rec", "次要但新", importance=0.4, recency=0.9),
    ]
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(_layers(records), budget=10)
    # 0.9*0.2=0.18 vs 0.4*0.9=0.36 → 次要但新排前
    assert result[0].record_id == "low_imp_high_rec"


def test_relevance_boosts_matching_record() -> None:
    records = [
        _rec("unrelated", "今天天气不错", importance=0.9, recency=0.9),
        _rec("related", "用户身份：架构师", importance=0.6, recency=0.5),
    ]
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(_layers(records), budget=10, query="架构师")
    # 相关性提升使匹配记录排前
    assert result[0].record_id == "related"


def test_empty_query_keeps_neutral_relevance() -> None:
    records = [
        _rec("a", "事实A", importance=0.8, recency=0.9),
        _rec("b", "事实B", importance=0.9, recency=0.8),
    ]
    policy = LayeredRetrievalPolicy()
    result = policy.retrieve(_layers(records), budget=10, query="")
    # 无查询时按 recency×importance：a=0.72, b=0.72 平手 → 稳定顺序
    assert len(result) == 2
