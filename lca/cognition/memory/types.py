"""ADR-0277 typed 记忆对象：三类记忆 + consolidation 决策 + 检索评分。

对应 ADR §2.1（EpisodicTrace / SemanticClaim / ProceduralRule）、
§2.3（ConsolidationRecord）与检索评分 SSOT（ScoredCandidate）。

所有类型均为 frozen dataclass，non-lossy：失效标记不删除。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

__all__ = [
    "W_CUE",
    "W_RECENCY",
    "W_SALIENCE",
    "W_SEMANTIC",
    "ConsolidationRecord",
    "EpisodicTrace",
    "ProceduralRule",
    "ScoredCandidate",
    "SemanticClaim",
    "WorkingMemoryPercept",
]

# ADR-0277 检索评分权重（已裁决，P3 评分 SSOT）：
# score = W_SEMANTIC*semantic_sim + W_RECENCY*recency
#       + W_SALIENCE*salience + W_CUE*cue_match
W_SEMANTIC = 0.4
W_SALIENCE = 0.25
W_RECENCY = 0.2
W_CUE = 0.15


def _require_unit_interval(name: str, value: float) -> None:
    """校验 0..1 闭区间，越界抛 ValueError。"""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} 必须在 0..1 之间，实际={value!r}")


def _require_non_empty(name: str, value: str) -> None:
    """校验非空字符串（全空白也算空），为空抛 ValueError。"""
    if not value or not value.strip():
        raise ValueError(f"{name} 不允许为空")


@dataclass(frozen=True)
class WorkingMemoryPercept:
    """工作记忆感知（Baddeley working memory）：Run 内瞬态激活目标与焦点实体。"""

    task_goal: str
    focal_entities: tuple[str, ...] = ()
    active_cues: tuple[str, ...] = ()
    observed_at_ms: int = 0

    def __post_init__(self) -> None:
        _require_non_empty("task_goal", self.task_goal)


@dataclass(frozen=True)
class EpisodicTrace:
    """情景记忆：何时何地何事（Tulving episodic，对应 LCA 的 L1 日志层）。

    what 保存事件原文（non-lossy）；when 是世界时间（Zep 的 t_valid），
    ingested_at 是系统时间（Zep 的 t_created）。
    """

    id: str
    when: datetime
    ingested_at: datetime
    who: tuple[str, ...]  # 相关人物
    what: str  # 事件原文（non-lossy）
    salience: float  # 显著性 0..1（编码门控用）
    associated_tool: str | None = None
    ttl_days: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty("what", self.what)
        _require_unit_interval("salience", self.salience)


@dataclass(frozen=True)
class SemanticClaim:
    """语义记忆：提炼出的事实断言（Tulving semantic，对应 LCA 的 L2 MEMORY.md 层）。

    双时间线（Zep 式）：valid_from/valid_to 描述"何时为真"；
    被取代时填 valid_to，永不删除（C4）。
    """

    id: str
    claim: str
    confidence: float  # 0..1
    sources: tuple[str, ...]  # provenance：trace id / 文档 / 对话轮次
    valid_from: datetime | None
    valid_to: datetime | None = None  # None=当前有效；被取代时填值，不删除
    supersedes: str | None = None  # 被取代的 claim id（Zep 式非丢失）
    category: str = "fact"  # identity | preference | fact | constraint
    dedupe_key: str | None = None  # 抽象维度键（如 preference:tech_stack）
    sensitivity: Literal["normal", "high"] = "normal"  # 表达分寸防火墙用

    def __post_init__(self) -> None:
        _require_non_empty("claim", self.claim)
        _require_unit_interval("confidence", self.confidence)

    def is_valid_at(self, ts: datetime) -> bool:
        """P6 双时间线查询：ts 时刻该 claim 是否有效。

        valid_from 为 None 视为无下界（一直有效到 ts 之前）；
        valid_to 为 None 表示当前仍有效。
        """
        if self.valid_from is not None and ts < self.valid_from:
            return False
        return self.valid_to is None or ts < self.valid_to


@dataclass(frozen=True)
class ProceduralRule:
    """程序性记忆：怎么做（Soar procedural，对应 LCA 的 skills 层）。"""

    id: str
    trigger: str  # 何时适用（自然语言 + 可选的结构化条件）
    action: str  # 做什么
    scope: str  # 适用范围：lane / 全局 / 某项目

    def __post_init__(self) -> None:
        _require_non_empty("action", self.action)


@dataclass(frozen=True)
class ConsolidationRecord:
    """remember 阶段的显式决策审计记录（Mem0 四操作升级为认知语义版）。

    每次 remember 产出一条，进审计日志（C5）。
    """

    decision: Literal["encode", "link", "decay", "schema"]
    target_id: str
    rationale: str  # 非空（C5 审计要求）

    def __post_init__(self) -> None:
        _require_non_empty("rationale", self.rationale)


@dataclass(frozen=True)
class ScoredCandidate:
    """检索候选的 ACT-R 式评分载体（C3 评分 SSOT）。

    score = W_SEMANTIC*semantic_sim + W_RECENCY*recency
          + W_SALIENCE*salience + W_CUE*cue_match
    """

    item_id: str
    kind: Literal["episodic", "semantic", "procedural"]
    semantic_sim: float
    recency: float
    salience: float
    cue_match: float
    score: float  # 加权总分

    def __post_init__(self) -> None:
        _require_unit_interval("semantic_sim", self.semantic_sim)
        _require_unit_interval("recency", self.recency)
        _require_unit_interval("salience", self.salience)
        _require_unit_interval("cue_match", self.cue_match)
        _require_unit_interval("score", self.score)
