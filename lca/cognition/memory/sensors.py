"""ADR-0277 Phase 2：perceive 记忆传感器注册表。

对应 ADR §2.2（EpisodicSensor / SemanticSensor / RelationSensor）与 §3 契约：

- C1 类型铁律：任何记忆进入 perceive 必须包装为 typed percept，禁止裸文本注入；
  违规 = fail-closed（不上报，而不是降级为文本）。
- C2 来源诚实：每个 percept 必带 ``provenance + confidence``；
  confidence < 0.3 的不上报，由 sensor 显式返回 ``NoRecall``。

所有 sensor 构造时注入内存中的数据集合（可测试、不碰外部存储）。
sensor 的 perceive 永远返回「typed percept 列表」或「单个 NoRecall」，
绝不返回空列表让调用方猜。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Union

from lca.cognition.memory.types import EpisodicTrace, SemanticClaim

__all__ = [
    "MIN_CONFIDENCE",
    "EpisodicPercept",
    "SemanticPercept",
    "RelationPercept",
    "Percept",
    "NoRecall",
    "EpisodicSensor",
    "SemanticSensor",
    "RelationSensor",
    "MemorySensor",
    "MemorySensorRegistry",
]

# C2 上报铁律：confidence 低于此阈值的 percept 不上报（fail-closed），
# sensor 显式返回 NoRecall。SSOT：sensor 与 registry 共用同一常量。
MIN_CONFIDENCE = 0.3


def _require_unit_interval(name: str, value: float) -> None:
    """校验 0..1 闭区间，越界抛 ValueError。"""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} 必须在 0..1 之间，实际={value!r}")


def _require_non_empty(name: str, value: str) -> None:
    """校验非空字符串（全空白也算空），为空抛 ValueError。"""
    if not value or not value.strip():
        raise ValueError(f"{name} 不允许为空")


@dataclass(frozen=True)
class EpisodicPercept:
    """情景感知：一次被召回的情景记忆（C1 typed，禁止裸文本）。

    confidence 取 recency_score：越久远的记忆，召回置信度越低
    （Ebbinghaus 遗忘曲线的诚实表达——"我想不起来了"而不是"硬信旧记忆"）。
    """

    trace: EpisodicTrace
    recency_score: float  # (1+age_hours)^-0.5，ADR C3 d=0.5 幂律衰减
    provenance: str  # f"episodic:{trace.id}"
    confidence: float  # = recency_score

    def __post_init__(self) -> None:
        _require_non_empty("provenance", self.provenance)
        _require_unit_interval("recency_score", self.recency_score)
        _require_unit_interval("confidence", self.confidence)


@dataclass(frozen=True)
class SemanticPercept:
    """语义感知：一条被召回的事实断言。

    confidence 直接取 claim.confidence（C2：置信度是断言自带的属性，
    sensor 不得凭空抬高）；provenance 取自 claim.sources（C2 来源诚实）。
    """

    claim: SemanticClaim
    provenance: str  # "; ".join(claim.sources)；sources 为空时回退 f"semantic:{claim.id}"
    confidence: float  # = claim.confidence

    def __post_init__(self) -> None:
        _require_non_empty("provenance", self.provenance)
        _require_unit_interval("confidence", self.confidence)


@dataclass(frozen=True)
class RelationPercept:
    """人物/群组上下文感知（v1：构造时注入的静态映射，接 people/groups）。

    静态注入的映射视为确定性知识，confidence 固定 1.0；
    命中即上报（人名精确命中不存在"低置信度"的中间态）。
    """

    person: str
    context: str
    provenance: str  # 静态映射来源，默认 "relations:static"
    confidence: float  # 固定 1.0

    def __post_init__(self) -> None:
        _require_non_empty("person", self.person)
        _require_non_empty("provenance", self.provenance)
        _require_unit_interval("confidence", self.confidence)


# 任一 typed 感知（C1 类型铁律的"类型"全集）。
Percept = Union[EpisodicPercept, SemanticPercept, RelationPercept]

_PERCEPT_TYPES = (EpisodicPercept, SemanticPercept, RelationPercept)


@dataclass(frozen=True)
class NoRecall:
    """sensor 明确返回"无召回"的 sentinel（C2 诚实的"我不记得"）。

    两种触发情形：cues 无命中；或命中候选的 confidence 全部低于
    MIN_CONFIDENCE（fail-closed：不上报，也绝不降级为文本上报）。
    调用方收到 NoRecall 即知道"sensor 尽力了但没有可信记忆"，
    而不是对着空列表猜。
    """

    reason: str  # 非空：为什么无召回

    def __post_init__(self) -> None:
        _require_non_empty("reason", self.reason)


def _recency_score(when: datetime, now: datetime) -> float:
    """新近性幂律衰减（ADR C3，d=0.5）：``(1 + age_hours) ** -0.5``。

    ``when`` 在未来时 age 按 0 处理（recency_score = 1.0）。
    """
    age_hours = max(0.0, (now - when).total_seconds() / 3600.0)
    return (1.0 + age_hours) ** -0.5


def _cue_hits(cue: str, text: str) -> bool:
    """单个 cue 是否命中一段文本：大小写不敏感，双向子串匹配。

    双向是因为 cue 常是自然语言短句（"李超在长沙" 应命中人物名 "李超"），
    而 trace.what 是长文本（cue 应是其子串）。空 cue / 空文本永不命中。
    """
    c = cue.casefold().strip()
    t = text.casefold().strip()
    if not c or not t:
        return False
    return c in t or t in c


def _cue_hit_count(cues: list[str], *texts: str) -> int:
    """cues 中命中任一文本的有几个（去重计数，用于排序主关键字）。"""
    return sum(1 for cue in cues if any(_cue_hits(cue, t) for t in texts))


def _fail_closed_no_recall(
    percepts: list[Percept], reason: str
) -> list[Union[Percept, NoRecall]]:
    """C2 门控：过滤 confidence < MIN_CONFIDENCE 的 percept。

    过滤后无剩余 → 显式返回 [NoRecall]（fail-closed），
    绝不返回空列表，也绝不把低置信度候选降级上报。
    """
    kept = [p for p in percepts if p.confidence >= MIN_CONFIDENCE]
    if kept:
        return kept
    return [NoRecall(reason=reason)]


class EpisodicSensor:
    """情景传感器：按 cues 文本命中 trace 的 who/what，按「命中数→新近性」排序。

    构造时注入内存中的 traces（可测试、不碰外部存储）。
    """

    def __init__(self, traces: list[EpisodicTrace]) -> None:
        self._traces = list(traces)

    def perceive(
        self, cues: list[str], now: datetime, limit: int = 5
    ) -> list[Union[EpisodicPercept, NoRecall]]:
        """召回与 cues 相关的情景记忆。

        返回 typed percept 列表，或单个 NoRecall（无命中 / 命中者
        recency 置信度全部低于阈值）。
        """
        scored: list[tuple[int, float, EpisodicTrace]] = []
        for trace in self._traces:
            n = _cue_hit_count(cues, trace.what, *trace.who)
            if n == 0:
                continue
            scored.append((n, _recency_score(trace.when, now), trace))
        if not scored:
            return [NoRecall(reason=f"cues 未命中任何情景记忆：{cues!r}")]
        scored.sort(key=lambda s: (-s[0], -s[1]))
        percepts = [
            EpisodicPercept(
                trace=trace,
                recency_score=recency,
                provenance=f"episodic:{trace.id}",
                confidence=recency,
            )
            for _, recency, trace in scored[: max(limit, 0)]
        ]
        return _fail_closed_no_recall(
            percepts, reason="命中的情景记忆 recency 置信度均低于 0.3（fail-closed，不上报）"
        )


class SemanticSensor:
    """语义传感器：按主题查 claims。

    默认只返回当前有效集（``valid_to IS NULL`` 且 ``is_valid_at(now)``）；
    显式传入 ``as_of`` 时做 point-in-time 查询（P6 双时间线的基础，
    被取代的历史 claim 可查回，Zep 式"失效不删除"）。
    """

    def __init__(self, claims: list[SemanticClaim]) -> None:
        self._claims = list(claims)

    def perceive(
        self,
        cues: list[str],
        now: datetime,
        limit: int = 5,
        as_of: datetime | None = None,
    ) -> list[Union[SemanticPercept, NoRecall]]:
        """查询与 cues 相关的语义断言。

        ``as_of=None``（默认）：只查当前有效集；
        ``as_of`` 显式传入：查该时刻有效的 claim（含已被取代的历史版本）。
        返回 typed percept 列表，或单个 NoRecall。
        """
        if as_of is None:
            candidates = [
                c for c in self._claims if c.valid_to is None and c.is_valid_at(now)
            ]
            scope = "当前有效集"
        else:
            candidates = [c for c in self._claims if c.is_valid_at(as_of)]
            scope = f"as_of={as_of.isoformat()}"
        scored: list[tuple[int, SemanticClaim]] = []
        for claim in candidates:
            n = _cue_hit_count(cues, claim.claim)
            if n > 0:
                scored.append((n, claim))
        if not scored:
            return [NoRecall(reason=f"cues 在{scope}中未命中任何语义断言：{cues!r}")]
        scored.sort(key=lambda s: (-s[0], -s[1].confidence))
        percepts = [
            SemanticPercept(
                claim=claim,
                provenance="; ".join(claim.sources)
                if claim.sources
                else f"semantic:{claim.id}",
                confidence=claim.confidence,
            )
            for _, claim in scored[: max(limit, 0)]
        ]
        return _fail_closed_no_recall(
            percepts, reason="命中的语义断言置信度均低于 0.3（fail-closed，不降级上报）"
        )


class RelationSensor:
    """人物/群组传感器：按 cues 命中人物名（v1 静态映射，接 people/groups）。

    构造时注入 ``{人物名: 上下文}`` 静态映射；命中即上报 RelationPercept，
    无命中返回 NoRecall。
    """

    def __init__(
        self, relations: dict[str, str], provenance: str = "relations:static"
    ) -> None:
        _require_non_empty("provenance", provenance)
        self._relations = dict(relations)
        self._provenance = provenance

    def perceive(
        self, cues: list[str], now: datetime, limit: int = 5
    ) -> list[Union[RelationPercept, NoRecall]]:
        hits = [
            (person, context)
            for person, context in self._relations.items()
            if _cue_hit_count(cues, person) > 0
        ]
        if not hits:
            return [NoRecall(reason=f"cues 未命中任何已知人物：{cues!r}")]
        hits.sort(key=lambda h: h[0])
        return [
            RelationPercept(
                person=person,
                context=context,
                provenance=self._provenance,
                confidence=1.0,
            )
            for person, context in hits[: max(limit, 0)]
        ]


class MemorySensor(Protocol):
    """perceive 传感器的结构化协议：``perceive(cues, now, limit=5)``。

    SemanticSensor 多一个可选的 ``as_of`` 关键字参数，仍符合本协议
    （registry 只按 ``perceive(cues, now)`` 调用）。
    """

    def perceive(
        self, cues: list[str], now: datetime, limit: int = 5
    ) -> list: ...  # noqa: E704


class MemorySensorRegistry:
    """perceive 阶段的记忆传感器注册表（ADR §2.2）。

    两道门：
    1. C2 门控（fail-closed）：confidence < MIN_CONFIDENCE 的 percept 被过滤，
       不上报、不降级为文本；NoRecall sentinel 原样保留（它不是 percept）。
    2. token 预算 ``max_percepts``（呼应 ADR §2.4 todo-29 A2 wire 预算）：
       超预算时全局按 confidence 从高到低截断。

    ``perceive_all`` 返回 ``{sensor名: [...] }``（保持注册顺序）；
    某 sensor 的 percept 被预算截光时给空列表（预算耗尽信号），
    sensor 本人报告 NoRecall 时原样透出。
    """

    def __init__(self, max_percepts: int = 20) -> None:
        if max_percepts < 1:
            raise ValueError(f"max_percepts 必须 >= 1，实际={max_percepts!r}")
        self._sensors: dict[str, MemorySensor] = {}
        self.max_percepts = max_percepts

    def register(self, name: str, sensor: MemorySensor) -> None:
        """注册一个 sensor；重名注册抛 ValueError（显式优于静默覆盖）。"""
        _require_non_empty("name", name)
        if not callable(getattr(sensor, "perceive", None)):
            raise TypeError(f"sensor 必须实现 perceive(cues, now, limit=5) 方法：{name!r}")
        if name in self._sensors:
            raise ValueError(f"sensor 名称已注册：{name!r}")
        self._sensors[name] = sensor

    def perceive_all(
        self, cues: list[str], now: datetime
    ) -> dict[str, list[Union[Percept, NoRecall]]]:
        """触发全部 sensor 感知，依次过 C2 门控与 token 预算，返回分组结果。"""
        # 1) 各 sensor 独立感知
        raw: dict[str, list] = {}
        for name, sensor in self._sensors.items():
            items = sensor.perceive(cues, now)
            raw[name] = list(items) if items is not None else []
        # 2) C2 门控：过滤低置信度 percept（第二道门；合规 sensor 自己已过滤过）
        gated: dict[str, tuple[list[Percept], list[NoRecall]]] = {}
        pool: list[tuple[float, str, Percept]] = []
        for name, items in raw.items():
            percepts = [i for i in items if isinstance(i, _PERCEPT_TYPES)]
            norc = [i for i in items if isinstance(i, NoRecall)]
            percepts = [p for p in percepts if p.confidence >= MIN_CONFIDENCE]
            gated[name] = (percepts, norc)
            pool.extend((p.confidence, name, p) for p in percepts)
        # 3) token 预算：全局按 confidence 从高到低截断
        pool.sort(key=lambda t: t[0], reverse=True)
        kept_ids = {id(p) for _, _, p in pool[: self.max_percepts]}
        # 4) 组装（保持注册顺序；预算截光的 sensor 给空列表）
        out: dict[str, list[Union[Percept, NoRecall]]] = {}
        for name in self._sensors:
            percepts, norc = gated[name]
            alive = sorted(
                (p for p in percepts if id(p) in kept_ids),
                key=lambda p: p.confidence,
                reverse=True,
            )
            out[name] = alive if alive else norc
        return out
