"""ADR-0277 Phase 3：检索评分 SSOT（C3）。

对应 ADR §2.2 检索评分公式与 §3 C3：
    score = W_SEMANTIC * semantic_sim + W_SALIENCE * salience
          + W_RECENCY * recency_decay(age_hours) + W_CUE * cue_match
    recency_decay(age_hours, d) = (1 + max(age_hours, 0)) ** (-d)
    （d 默认 0.5，ACT-R base-level 幂律衰减；t = 年龄小时数 + 1，保证 t >= 1）。

设计要点（fail-closed）：
- WeightedScorer 是默认主路径：纯确定性公式，无模型、无网络调用。
- LayaScorer 是可插拔增强：engine 不可用时 score() 直接抛 RuntimeError，
  绝不静默降级为加权分数（降级只能由 HybridScorer 的显式回退逻辑决定）。
- HybridScorer：加权给全量打分取 top_k → Laya 重排；任一候选
  laya_confidence 低于阈值则该候选回退确定性分数（保守回退）。
- ShadowComparator：双轨并行打分 + JSONL 留痕；在 shadow 数据证明 Laya
  更优之前，Laya 永不做主 scorer（见 ShadowComparator docstring）。
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from .types import (
    W_CUE,
    W_RECENCY,
    W_SALIENCE,
    W_SEMANTIC,
    ScoredCandidate,
)

try:  # laya_backend 由 P4 并行实现；导入失败即视为 engine 不可用
    from .laya_backend import LayaScore, LayaScoreEngine
except ImportError:  # pragma: no cover - 缺模块是预期的正常分支
    LayaScore = None  # type: ignore[assignment]
    LayaScoreEngine = None  # type: ignore[assignment]

__all__ = [
    "DEFAULT_SHADOW_LOG",
    "HybridScorer",
    "LayaScoredItem",
    "LayaScorer",
    "MemoryScorer",
    "ShadowComparator",
    "ShadowRecord",
    "WeightedScorer",
    "build_candidate",
]

DEFAULT_SHADOW_LOG = "./shadow_scores.jsonl"
_LAYA_LABEL_MAX = 4.0  # Laya legend：0=无关 … 4=直接回答
_WEIGHT_TOL = 1e-9  # 权重和断言容差


@runtime_checkable
class MemoryScorer(Protocol):
    """检索评分器协议（ADR-0277 C3 评分 SSOT 的执行面）。

    实现者接收一批候选，返回按 score 降序排列的**新** ScoredCandidate 列表
    （score 字段填好；frozen dataclass 用 dataclasses.replace 构造新对象，
    不修改输入列表及其元素）。
    """

    def score(
        self, query: str, candidates: list[ScoredCandidate]
    ) -> list[ScoredCandidate]:
        """打分并按 score 降序返回新列表。"""
        ...


def _check_weights(
    w_semantic: float, w_salience: float, w_recency: float, w_cue: float
) -> None:
    """断言四权重和 ≈ 1.0，否则抛 AssertionError（ADR-0277 权重铁律）。"""
    total = w_semantic + w_salience + w_recency + w_cue
    assert abs(total - 1.0) <= _WEIGHT_TOL, f"评分权重和必须 ≈ 1.0，实际={total!r}"


class WeightedScorer(MemoryScorer):
    """ACT-R 式确定性加权评分器（默认主路径，fail-closed 底座）。

    score = w_semantic*semantic_sim + w_salience*salience
          + w_recency*recency + w_cue*cue_match

    权重默认取 ADR-0277 已裁决值（types.py 的 W_* 常量），构造时可覆盖；
    构造时断言权重和 ≈ 1.0。纯公式计算，不依赖模型与网络。
    """

    def __init__(
        self,
        *,
        w_semantic: float = W_SEMANTIC,
        w_salience: float = W_SALIENCE,
        w_recency: float = W_RECENCY,
        w_cue: float = W_CUE,
        decay_d: float = 0.5,
    ) -> None:
        _check_weights(w_semantic, w_salience, w_recency, w_cue)
        if decay_d <= 0:
            raise ValueError(f"decay_d 必须 > 0，实际={decay_d!r}")
        self.w_semantic = w_semantic
        self.w_salience = w_salience
        self.w_recency = w_recency
        self.w_cue = w_cue
        self.decay_d = decay_d

    @staticmethod
    def recency_decay(age_hours: float, d: float = 0.5) -> float:
        """ACT-R base-level 式幂律衰减：(1 + max(age_hours, 0)) ** (-d)。

        t = 年龄小时数 + 1，保证 t >= 1；age_hours=0 时返回 1.0（无衰减）；
        负的 age_hours 按 0 处理。d 默认 0.5（ACT-R base-level），可配置。
        """
        if d <= 0:
            raise ValueError(f"d 必须 > 0，实际={d!r}")
        return (1.0 + max(age_hours, 0.0)) ** (-d)

    def score_one(self, candidate: ScoredCandidate) -> float:
        """单个候选的加权总分（确定性公式）。"""
        return (
            self.w_semantic * candidate.semantic_sim
            + self.w_salience * candidate.salience
            + self.w_recency * candidate.recency
            + self.w_cue * candidate.cue_match
        )

    def score(
        self, query: str, candidates: list[ScoredCandidate]
    ) -> list[ScoredCandidate]:
        """全量加权打分，按 score 降序返回新列表。

        query 在确定性路径中不参与计算（保留参数以满足 MemoryScorer 协议）。
        """
        scored = [dataclasses.replace(c, score=self.score_one(c)) for c in candidates]
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored


def build_candidate(
    item_id: str,
    kind: Literal["episodic", "semantic", "procedural"],
    *,
    semantic_sim: float,
    age_hours: float,
    salience: float,
    cue_match: float,
    d: float = 0.5,
    weights: tuple[float, float, float, float] | None = None,
) -> ScoredCandidate:
    """由原始特征构造 ScoredCandidate。

    age_hours 经 WeightedScorer.recency_decay 换算为 recency 分量；
    score 按加权公式一次算好。weights 为
    (w_semantic, w_salience, w_recency, w_cue)，默认用 ADR-0277 已裁决的
    模块常量；若使用自定义权重的 WeightedScorer，请把它的权重传进来，
    否则两者口径不一致。
    """
    w_sem, w_sal, w_rec, w_cue = weights or (W_SEMANTIC, W_SALIENCE, W_RECENCY, W_CUE)
    _check_weights(w_sem, w_sal, w_rec, w_cue)
    recency = WeightedScorer.recency_decay(age_hours, d)
    score = (
        w_sem * semantic_sim + w_sal * salience + w_rec * recency + w_cue * cue_match
    )
    return ScoredCandidate(
        item_id=item_id,
        kind=kind,
        semantic_sim=semantic_sim,
        recency=recency,
        salience=salience,
        cue_match=cue_match,
        score=score,
    )


@dataclass(frozen=True)
class LayaScoredItem:
    """Laya 单候选打分明细。

    candidate 保留输入原样（其 score 为输入时的分数，通常是加权确定性分数）；
    laya_score 为 label/4.0*confidence 映射后的分数。
    """

    candidate: ScoredCandidate
    label: int
    confidence: float
    laya_score: float


class LayaScorer(MemoryScorer):
    """Laya 驱动的评分器（可插拔增强，非主路径）。

    label→分数映射：label / 4.0 * laya_confidence
    （legend：0=无关 … 4=直接回答；confidence 为已温度校准的置信度）。

    engine 为 None 或 not is_available() 时 score() 直接抛
    RuntimeError("Laya engine unavailable")——fail-closed，不许静默降级为
    加权分数。需要"不可用时回退"语义请用 HybridScorer。
    """

    def __init__(
        self,
        engine: LayaScoreEngine | None,
        *,
        text_of: Callable[[ScoredCandidate], str] | None = None,
    ) -> None:
        self._engine = engine
        # 候选 → 送给 Laya 的文本；默认用 item_id（调用方可注入真实文本解析）
        self.text_of: Callable[[ScoredCandidate], str] = (
            text_of if text_of is not None else (lambda c: c.item_id)
        )

    def is_usable(self) -> bool:
        """engine 存在且可用（is_available() 为真）。"""
        engine = self._engine
        return engine is not None and bool(engine.is_available())

    @staticmethod
    def _map_score(label: int, confidence: float) -> float:
        """label→分数映射，并钳制到 0..1（保护 ScoredCandidate 的区间校验）。"""
        return min(max((label / _LAYA_LABEL_MAX) * confidence, 0.0), 1.0)

    def score_detailed(
        self,
        query: str,
        candidates: list[ScoredCandidate],
        *,
        text_of: Callable[[ScoredCandidate], str] | None = None,
    ) -> list[LayaScoredItem]:
        """逐候选返回打分明细，按 laya_score 降序。

        engine 不可用时抛 RuntimeError（fail-closed）。
        """
        engine = self._engine
        if engine is None or not engine.is_available():
            raise RuntimeError("Laya engine unavailable")
        resolve = text_of if text_of is not None else self.text_of
        texts = [resolve(c) for c in candidates]
        results = engine.score_relevance(query, texts)
        items = [
            LayaScoredItem(
                candidate=c,
                label=r.label,
                confidence=r.confidence,
                laya_score=self._map_score(r.label, r.confidence),
            )
            for c, r in zip(candidates, results)
        ]
        items.sort(key=lambda it: it.laya_score, reverse=True)
        return items

    def score(
        self, query: str, candidates: list[ScoredCandidate]
    ) -> list[ScoredCandidate]:
        """Laya 打分并按 laya_score 降序返回新列表；engine 不可用时抛 RuntimeError。"""
        return [
            dataclasses.replace(item.candidate, score=item.laya_score)
            for item in self.score_detailed(query, candidates)
        ]


@dataclass(frozen=True)
class ShadowRecord:
    """一次 shadow 对比中单个候选的双轨打分记录（进 JSONL 审计）。"""

    query: str
    candidate_id: str
    weighted_score: float
    laya_label: int
    laya_confidence: float
    agreement: bool  # 两套排序的 top-1 是否相同

    def to_dict(self) -> dict[str, object]:
        """转 JSON 可序列化字典（JSONL 行内容）。"""
        return {
            "query": self.query,
            "candidate_id": self.candidate_id,
            "weighted_score": self.weighted_score,
            "laya_label": self.laya_label,
            "laya_confidence": self.laya_confidence,
            "agreement": self.agreement,
        }


class ShadowComparator:
    """Shadow 模式比较器：双轨并行打分，结果追加写 JSONL。

    设计声明：在 shadow 数据证明 Laya 更优之前，Laya 永不做主 scorer——
    本类只做观测与留痕，不改变任何线上排序，不参与打分决策。

    agreement 定义：加权排序与 Laya 排序的 top-1 candidate_id 相同。
    空候选集时 agreement=False（无数据不断言一致）。
    engine 不可用时 compare() 直接抛 RuntimeError（与 LayaScorer.score
    一致的 fail-closed 语义）：观测不到不可用的 engine。
    """

    def __init__(self, log_path: str | Path = DEFAULT_SHADOW_LOG) -> None:
        self.log_path = Path(log_path)

    def compare(
        self,
        query: str,
        candidates_text: Sequence[tuple[ScoredCandidate, str]],
        weighted: MemoryScorer,
        laya: LayaScorer,
    ) -> list[ShadowRecord]:
        """同时跑加权与 Laya 两套打分，写 ShadowRecord 进 JSONL（追加）并返回。

        candidates_text：(ScoredCandidate, 文本) 二元组序列——加权侧用
        candidate 打分，Laya 侧用文本打分；item_id 必须唯一。
        """
        candidates = [c for c, _ in candidates_text]
        texts = {c.item_id: text for c, text in candidates_text}
        weighted_ranked = weighted.score(query, candidates)
        weighted_scores = {c.item_id: c.score for c in weighted_ranked}
        detailed = laya.score_detailed(
            query, candidates, text_of=lambda c: texts[c.item_id]
        )
        weighted_top = weighted_ranked[0].item_id if weighted_ranked else None
        laya_top = detailed[0].candidate.item_id if detailed else None
        agreement = (
            weighted_top is not None
            and laya_top is not None
            and weighted_top == laya_top
        )
        records = [
            ShadowRecord(
                query=query,
                candidate_id=item.candidate.item_id,
                weighted_score=weighted_scores[item.candidate.item_id],
                laya_label=item.label,
                laya_confidence=item.confidence,
                agreement=agreement,
            )
            for item in detailed
        ]
        self._append_jsonl(records)
        return records

    def _append_jsonl(self, records: list[ShadowRecord]) -> None:
        """追加写 JSONL；父目录不存在时创建（默认 ./ 路径跳过创建）。"""
        if self.log_path.parent != Path("."):
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


class HybridScorer(MemoryScorer):
    """加权确定性打分 + Laya 重排的混合评分器。

    流程：weighted 给全量打分取 top_k → laya 对 top_k 重排；
    任一候选 laya_confidence < threshold → 该候选回退确定性（加权）分数，
    即保守回退。laya 为 None 或 engine 不可用时整体回退加权排序——
    HybridScorer 永不因 Laya 问题抛错（抛错是 LayaScorer.score 的职责）。

    shadow 模式默认开启：laya 实际参与重排时，并行跑
    ShadowComparator.compare 写 JSONL 留痕；shadow 日志失败不影响打分结果
    （可观测性降级，fail-open 仅限日志本身）。
    """

    def __init__(
        self,
        weighted: WeightedScorer,
        laya: LayaScorer | None,
        top_k: int = 10,
        laya_confidence_threshold: float = 0.6,
        shadow: ShadowComparator | bool | None = True,
    ) -> None:
        if top_k < 1:
            raise ValueError(f"top_k 必须 >= 1，实际={top_k!r}")
        if not 0.0 <= laya_confidence_threshold <= 1.0:
            raise ValueError(
                f"laya_confidence_threshold 必须在 0..1 之间，"
                f"实际={laya_confidence_threshold!r}"
            )
        self._weighted = weighted
        self._laya = laya
        self._top_k = top_k
        self._threshold = laya_confidence_threshold
        if shadow is True:
            self._shadow: ShadowComparator | None = ShadowComparator()
        elif shadow is False or shadow is None:
            self._shadow = None
        else:
            self._shadow = shadow

    def score(
        self, query: str, candidates: list[ScoredCandidate]
    ) -> list[ScoredCandidate]:
        """混合打分：top_k 内 Laya 重排（含保守回退），整体按有效分数降序返回。"""
        ranked = self._weighted.score(query, candidates)  # 全量确定性打分，已降序
        top = ranked[: self._top_k]
        tail = ranked[self._top_k :]
        if self._laya is None or not self._laya.is_usable():
            return ranked  # 保守回退：整体用确定性分数
        detailed = self._laya.score_detailed(query, top)
        reranked: list[ScoredCandidate] = []
        for item in detailed:
            if item.confidence >= self._threshold:
                reranked.append(
                    dataclasses.replace(item.candidate, score=item.laya_score)
                )
            else:
                # 保守回退：该候选保留加权确定性分数
                reranked.append(item.candidate)
        if self._shadow is not None:
            try:
                pairs = [(c, self._laya.text_of(c)) for c in top]
                self._shadow.compare(query, pairs, self._weighted, self._laya)
            except Exception:
                pass  # shadow 是可观测性，不许影响检索
        final = reranked + tail
        final.sort(key=lambda c: c.score, reverse=True)
        return final
