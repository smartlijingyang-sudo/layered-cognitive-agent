"""ADR-0277 Phase 3 测试：检索评分 SSOT（C3）。

覆盖 ADR §4 A4：相同语义相似度下，更近 / 更高 salience 的排前面；
权重和断言；recency_decay 单调性与 age=0；LayaScorer 不可用时抛 RuntimeError；
HybridScorer 低 confidence 回退确定性分数；ShadowComparator 写 JSONL 且
agreement 计算正确。

Laya 侧不依赖真模型：本文件内定义 FakeEngine（实现 is_available /
score_relevance 鸭子类型接口），只断言回退逻辑与 label→分数映射公式。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pytest

from lca.cognition.memory.scoring import (
    DEFAULT_SHADOW_LOG,
    HybridScorer,
    LayaScorer,
    MemoryScorer,
    ShadowComparator,
    ShadowRecord,
    WeightedScorer,
    build_candidate,
)
from lca.cognition.memory.types import (
    W_CUE,
    W_RECENCY,
    W_SALIENCE,
    W_SEMANTIC,
    ScoredCandidate,
)


# ---------------------------------------------------------------------------
# 测试替身：FakeEngine（实现 LayaScoreEngine 的鸭子类型接口，不依赖真模型）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeLayaScore:
    label: int
    confidence: float


class FakeEngine:
    """LayaScoreEngine 测试替身：is_available / score_relevance 按预设返回。"""

    def __init__(
        self,
        available: bool = True,
        scores: dict[str, FakeLayaScore] | None = None,
        default: FakeLayaScore | None = None,
    ) -> None:
        self._available = available
        self._scores = dict(scores or {})
        self._default = default or FakeLayaScore(label=0, confidence=0.0)
        self.calls: list[tuple[str, list[str]]] = []

    def is_available(self) -> bool:
        return self._available

    def score_relevance(
        self, query: str, candidates: list[str], legend=None
    ) -> list[FakeLayaScore]:
        self.calls.append((query, list(candidates)))
        return [self._scores.get(text, self._default) for text in candidates]


def _cand(
    item_id: str,
    *,
    semantic_sim: float = 0.7,
    age_hours: float = 1.0,
    salience: float = 0.5,
    cue_match: float = 0.5,
    kind: str = "semantic",
) -> ScoredCandidate:
    return build_candidate(
        item_id,
        kind,  # type: ignore[arg-type]
        semantic_sim=semantic_sim,
        age_hours=age_hours,
        salience=salience,
        cue_match=cue_match,
    )


# ---------------------------------------------------------------------------
# WeightedScorer：A4 排序语义
# ---------------------------------------------------------------------------


def test_same_semantic_newer_ranks_first() -> None:
    """A4：相同语义相似度下，更近（age 小）的排前面。"""
    old = _cand("old", age_hours=200.0)
    new = _cand("new", age_hours=1.0)
    ranked = WeightedScorer().score("q", [old, new])
    assert [c.item_id for c in ranked] == ["new", "old"]
    assert ranked[0].score > ranked[1].score


def test_same_semantic_higher_salience_ranks_first() -> None:
    """A4：相同语义相似度下，更高 salience 的排前面。"""
    low = _cand("low", salience=0.1)
    high = _cand("high", salience=0.9)
    ranked = WeightedScorer().score("q", [low, high])
    assert [c.item_id for c in ranked] == ["high", "low"]


def test_score_formula_matches_adr() -> None:
    """score = W_SEMANTIC*ss + W_SALIENCE*sal + W_RECENCY*rec + W_CUE*cue。"""
    c = _cand("x", semantic_sim=0.8, age_hours=3.0, salience=0.6, cue_match=0.4)
    rec = WeightedScorer.recency_decay(3.0)
    assert c.recency == pytest.approx(rec)
    expected = W_SEMANTIC * 0.8 + W_SALIENCE * 0.6 + W_RECENCY * rec + W_CUE * 0.4
    assert c.score == pytest.approx(expected)


def test_score_returns_new_list_sorted_desc_without_mutating_input() -> None:
    """返回新列表、降序；输入列表与元素 score 不被修改。"""
    a = _cand("a", salience=0.9)
    b = _cand("b", salience=0.1)
    original_scores = [a.score, b.score]
    ranked = WeightedScorer().score("q", [b, a])
    assert ranked is not [b, a]
    assert [c.item_id for c in ranked] == ["a", "b"]
    assert ranked[0].score >= ranked[1].score
    assert [a.score, b.score] == original_scores  # 输入元素未被改动


def test_weights_sum_assertion() -> None:
    """权重和 != 1.0 时构造抛 AssertionError；合法覆盖正常工作。"""
    with pytest.raises(AssertionError):
        WeightedScorer(w_semantic=0.5, w_salience=0.5, w_recency=0.2, w_cue=0.1)
    ok = WeightedScorer(w_semantic=0.5, w_salience=0.2, w_recency=0.2, w_cue=0.1)
    assert ok.w_semantic == 0.5


def test_build_candidate_rejects_bad_weights() -> None:
    with pytest.raises(AssertionError):
        build_candidate(
            "x",
            "semantic",
            semantic_sim=0.5,
            age_hours=1.0,
            salience=0.5,
            cue_match=0.5,
            weights=(0.5, 0.5, 0.5, 0.5),
        )


# ---------------------------------------------------------------------------
# recency_decay：单调性 / 边界
# ---------------------------------------------------------------------------


def test_recency_decay_zero_age_is_one() -> None:
    assert WeightedScorer.recency_decay(0.0) == 1.0


def test_recency_decay_monotone_decreasing() -> None:
    d = WeightedScorer.recency_decay
    assert d(0.5) > d(5.0) > d(50.0) > d(500.0) > 0.0


def test_recency_decay_formula() -> None:
    assert WeightedScorer.recency_decay(10.0, d=1.0) == pytest.approx(1.0 / 11.0)
    assert WeightedScorer.recency_decay(3.0) == pytest.approx((1.0 + 3.0) ** -0.5)


def test_recency_decay_negative_age_clamped() -> None:
    assert WeightedScorer.recency_decay(-5.0) == 1.0


def test_recency_decay_invalid_d() -> None:
    with pytest.raises(ValueError):
        WeightedScorer.recency_decay(1.0, d=0.0)
    with pytest.raises(ValueError):
        WeightedScorer(decay_d=-1.0)


# ---------------------------------------------------------------------------
# 协议与 LayaScorer fail-closed
# ---------------------------------------------------------------------------


def test_scorers_satisfy_protocol() -> None:
    assert isinstance(WeightedScorer(), MemoryScorer)
    assert isinstance(LayaScorer(FakeEngine()), MemoryScorer)
    assert isinstance(
        HybridScorer(WeightedScorer(), LayaScorer(FakeEngine()), shadow=False),
        MemoryScorer,
    )


def test_laya_unavailable_raises_runtime_error() -> None:
    """engine 为 None 或 not is_available() → RuntimeError，不静默降级。"""
    cands = [_cand("a")]
    with pytest.raises(RuntimeError, match="Laya engine unavailable"):
        LayaScorer(None).score("q", cands)
    with pytest.raises(RuntimeError, match="Laya engine unavailable"):
        LayaScorer(FakeEngine(available=False)).score("q", cands)


def test_laya_is_usable() -> None:
    assert LayaScorer(FakeEngine(available=True)).is_usable()
    assert not LayaScorer(FakeEngine(available=False)).is_usable()
    assert not LayaScorer(None).is_usable()


def test_laya_label_to_score_mapping() -> None:
    """label→分数映射：label/4.0 * confidence；按映射分数降序。"""
    engine = FakeEngine(
        scores={"a": FakeLayaScore(label=3, confidence=0.8), "b": FakeLayaScore(label=4, confidence=0.5)}
    )
    ranked = LayaScorer(engine).score("q", [_cand("a"), _cand("b")])
    by_id = {c.item_id: c for c in ranked}
    assert by_id["a"].score == pytest.approx(3 / 4.0 * 0.8)  # 0.6
    assert by_id["b"].score == pytest.approx(4 / 4.0 * 0.5)  # 0.5
    assert [c.item_id for c in ranked] == ["a", "b"]
    # engine 收到的是候选文本（默认 text_of 取 item_id）
    assert engine.calls[0][1] == ["a", "b"]


# ---------------------------------------------------------------------------
# HybridScorer：保守回退
# ---------------------------------------------------------------------------


def _hybrid_candidates() -> list[ScoredCandidate]:
    # 加权排序固定为 a > b > c（salience 0.9/0.5/0.1 主导）
    return [
        _cand("a", age_hours=1.0, salience=0.9),
        _cand("b", age_hours=2.0, salience=0.5),
        _cand("c", age_hours=3.0, salience=0.1),
    ]


def test_hybrid_low_confidence_falls_back_to_weighted() -> None:
    """任一候选 laya_confidence < threshold → 该候选回退确定性分数。"""
    weighted = WeightedScorer()
    cands = _hybrid_candidates()
    weighted_ranked = weighted.score("q", cands)
    weighted_scores = {c.item_id: c.score for c in weighted_ranked}

    engine = FakeEngine(
        scores={
            "a": FakeLayaScore(label=4, confidence=0.1),  # 低 → 回退
            "b": FakeLayaScore(label=4, confidence=0.95),  # 高 → 采用 laya
        }
    )
    hybrid = HybridScorer(
        weighted, LayaScorer(engine), top_k=2, laya_confidence_threshold=0.6,
        shadow=False,
    )
    ranked = hybrid.score("q", cands)
    by_id = {c.item_id: c for c in ranked}
    assert by_id["a"].score == pytest.approx(weighted_scores["a"])  # 回退
    assert by_id["b"].score == pytest.approx(4 / 4.0 * 0.95)  # laya 分数
    assert by_id["c"].score == pytest.approx(weighted_scores["c"])  # top_k 之外
    assert [c.item_id for c in ranked] == ["b", "a", "c"]


def test_hybrid_laya_none_falls_back_to_weighted() -> None:
    """laya 为 None → 整体回退加权排序（不抛错）。"""
    weighted = WeightedScorer()
    cands = _hybrid_candidates()
    expected = [c.item_id for c in weighted.score("q", cands)]
    ranked = HybridScorer(weighted, None, shadow=False).score("q", cands)
    assert [c.item_id for c in ranked] == expected


def test_hybrid_laya_unavailable_falls_back_to_weighted() -> None:
    """engine 不可用 → 整体回退加权排序（不抛错，与 LayaScorer 的抛错区分）。"""
    weighted = WeightedScorer()
    cands = _hybrid_candidates()
    expected = [c.item_id for c in weighted.score("q", cands)]
    hybrid = HybridScorer(
        weighted, LayaScorer(FakeEngine(available=False)), shadow=False
    )
    ranked = hybrid.score("q", cands)
    assert [c.item_id for c in ranked] == expected
    assert ranked[0].score == pytest.approx(weighted.score("q", cands)[0].score)


def test_hybrid_top_k_limits_laya_calls() -> None:
    engine = FakeEngine()
    hybrid = HybridScorer(
        WeightedScorer(), LayaScorer(engine), top_k=1, shadow=False
    )
    hybrid.score("q", _hybrid_candidates())
    assert len(engine.calls) == 1
    assert len(engine.calls[0][1]) == 1  # 只把 top-1 送给 laya


def test_hybrid_invalid_args() -> None:
    with pytest.raises(ValueError):
        HybridScorer(WeightedScorer(), None, top_k=0, shadow=False)
    with pytest.raises(ValueError):
        HybridScorer(
            WeightedScorer(), None, laya_confidence_threshold=1.5, shadow=False
        )


# ---------------------------------------------------------------------------
# ShadowComparator：JSONL 留痕 + agreement
# ---------------------------------------------------------------------------


def _shadow_setup(
    tmp_path: Path, engine_scores: dict[str, FakeLayaScore]
) -> tuple[ShadowComparator, list[tuple[ScoredCandidate, str]], WeightedScorer, LayaScorer]:
    comparator = ShadowComparator(log_path=tmp_path / "shadow.jsonl")
    cands = _hybrid_candidates()  # 加权排序固定为 a > b > c
    pairs = [(c, c.item_id) for c in cands]  # 文本用 item_id 代替
    return comparator, pairs, WeightedScorer(), LayaScorer(FakeEngine(scores=engine_scores))


def test_shadow_writes_jsonl_and_agreement_true(tmp_path: Path) -> None:
    """双轨 top-1 相同 → agreement=True；JSONL 逐行可解析、字段齐全。"""
    comparator, pairs, weighted, laya = _shadow_setup(
        tmp_path, {"a": FakeLayaScore(4, 0.95), "b": FakeLayaScore(2, 0.8), "c": FakeLayaScore(0, 0.7)}
    )
    records = comparator.compare("q", pairs, weighted, laya)
    assert len(records) == 3
    assert all(isinstance(r, ShadowRecord) for r in records)
    assert all(r.agreement for r in records)

    lines = (tmp_path / "shadow.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    rows = [json.loads(line) for line in lines]
    assert {r["candidate_id"] for r in rows} == {"a", "b", "c"}
    row_a = next(r for r in rows if r["candidate_id"] == "a")
    assert row_a["query"] == "q"
    assert row_a["laya_label"] == 4
    assert row_a["laya_confidence"] == pytest.approx(0.95)
    assert row_a["weighted_score"] == pytest.approx(
        next(r.weighted_score for r in records if r.candidate_id == "a")
    )
    assert row_a["agreement"] is True


def test_shadow_agreement_false_when_top1_differs(tmp_path: Path) -> None:
    """Laya top-1（b）与加权 top-1（a）不同 → agreement=False。"""
    comparator, pairs, weighted, laya = _shadow_setup(
        tmp_path, {"a": FakeLayaScore(0, 0.9), "b": FakeLayaScore(4, 0.95), "c": FakeLayaScore(1, 0.5)}
    )
    records = comparator.compare("q", pairs, weighted, laya)
    assert all(r.agreement is False for r in records)


def test_shadow_appends_not_overwrites(tmp_path: Path) -> None:
    comparator, pairs, weighted, laya = _shadow_setup(
        tmp_path, {"a": FakeLayaScore(4, 0.9)}
    )
    comparator.compare("q1", pairs, weighted, laya)
    comparator.compare("q2", pairs, weighted, laya)
    lines = (tmp_path / "shadow.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 6  # 两次 compare，各 3 条，追加写


def test_shadow_default_log_path_constant() -> None:
    assert DEFAULT_SHADOW_LOG == "./shadow_scores.jsonl"
    assert ShadowComparator().log_path == Path("./shadow_scores.jsonl")


def test_shadow_empty_candidates_agreement_false(tmp_path: Path) -> None:
    comparator = ShadowComparator(log_path=tmp_path / "s.jsonl")
    records = comparator.compare("q", [], WeightedScorer(), LayaScorer(FakeEngine()))
    assert records == []
    assert comparator.log_path.read_text(encoding="utf-8") == ""


def test_hybrid_shadow_enabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """shadow 模式默认开：HybridScorer 走 laya 重排时默认写 ./shadow_scores.jsonl。"""
    monkeypatch.chdir(tmp_path)
    engine = FakeEngine(scores={"a": FakeLayaScore(4, 0.9)})
    hybrid = HybridScorer(WeightedScorer(), LayaScorer(engine), top_k=2)
    hybrid.score("q", _hybrid_candidates())
    log = tmp_path / "shadow_scores.jsonl"
    assert log.exists()
    assert len(log.read_text(encoding="utf-8").strip().split("\n")) == 2


def test_hybrid_shadow_disabled_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    engine = FakeEngine(scores={"a": FakeLayaScore(4, 0.9)})
    hybrid = HybridScorer(
        WeightedScorer(), LayaScorer(engine), top_k=2, shadow=False
    )
    hybrid.score("q", _hybrid_candidates())
    assert not (tmp_path / "shadow_scores.jsonl").exists()
