"""ADR-0277 Phase 2 测试：perceive 记忆传感器注册表。

无 mock，全真实行为：构造真实的 EpisodicTrace / SemanticClaim，
断言 sensor 与 registry 的真实输出。

覆盖：
- episodic 按时间排序召回（recency 幂律衰减公式）
- semantic 默认只返回当前有效集（valid_to 已填的旧 claim 被过滤）
- as_of point-in-time 能查回历史 claim（P6 双时间线）
- cues 无命中 → NoRecall（三种 sensor）
- confidence < 0.3 → NoRecall（fail-closed，不许降级上报）
- registry C2 门控过滤低 confidence（第二道门）
- registry max_percepts token 预算截断
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from lca.cognition.memory.sensors import (
    EpisodicPercept,
    EpisodicSensor,
    MemorySensorRegistry,
    NoRecall,
    RelationPercept,
    RelationSensor,
    SemanticPercept,
    SemanticSensor,
)
from lca.cognition.memory.types import EpisodicTrace, SemanticClaim

NOW = datetime(2026, 10, 3, 12, 0, 0)


def _trace(
    id: str,
    hours_ago: float,
    what: str,
    who: tuple[str, ...] = ("李超",),
    salience: float = 0.8,
) -> EpisodicTrace:
    when = NOW - timedelta(hours=hours_ago)
    return EpisodicTrace(
        id=id, when=when, ingested_at=when, who=who, what=what, salience=salience
    )


def _claim(
    id: str,
    claim: str,
    confidence: float = 0.9,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    sources: tuple[str, ...] = ("trace:t1",),
) -> SemanticClaim:
    return SemanticClaim(
        id=id,
        claim=claim,
        confidence=confidence,
        sources=sources,
        valid_from=valid_from,
        valid_to=valid_to,
        supersedes=None,
    )


# ---------- EpisodicSensor ----------


def test_episodic_recalls_sorted_by_recency() -> None:
    """相同 cue 命中多个 trace → 按新近性从新到旧排序；recency_score 符合幂律公式。"""
    sensor = EpisodicSensor(
        [
            _trace("t-old", hours_ago=3, what="李超问了部署流程"),
            _trace("t-new", hours_ago=0.5, what="李超又问了部署细节"),
            _trace("t-mid", hours_ago=1, what="部署文档更新了"),
        ]
    )
    result = sensor.perceive(["部署"], NOW)
    assert [p.trace.id for p in result] == ["t-new", "t-mid", "t-old"]
    for p, hours_ago in zip(result, [0.5, 1, 3]):
        assert isinstance(p, EpisodicPercept)
        assert p.recency_score == pytest.approx((1 + hours_ago) ** -0.5)
        # A1：percept 自带 provenance + confidence
        assert p.provenance == f"episodic:{p.trace.id}"
        assert p.confidence == pytest.approx(p.recency_score)


def test_episodic_cue_hit_on_who() -> None:
    """cue 命中 trace.who 中的人物名也能召回（双向子串匹配）。"""
    sensor = EpisodicSensor([_trace("t1", hours_ago=1, what="开了个会", who=("peter",))])
    result = sensor.perceive(["peter 在会上说了什么"], NOW)
    assert len(result) == 1
    assert isinstance(result[0], EpisodicPercept)
    assert result[0].trace.id == "t1"


def test_episodic_cue_miss_returns_norecall() -> None:
    """cues 无命中 → 显式 NoRecall，而不是空列表。"""
    sensor = EpisodicSensor([_trace("t1", hours_ago=1, what="李超问了部署")])
    result = sensor.perceive(["量子计算"], NOW)
    assert result != []
    assert len(result) == 1
    assert isinstance(result[0], NoRecall)
    assert result[0].reason.strip() != ""


def test_episodic_ancient_trace_fail_closed() -> None:
    """太久远的 trace（recency_score < 0.3）→ NoRecall，不上报。"""
    sensor = EpisodicSensor([_trace("t-ancient", hours_ago=48, what="李超问了部署")])
    # (1+48)^-0.5 ≈ 0.143 < 0.3
    result = sensor.perceive(["部署"], NOW)
    assert len(result) == 1
    assert isinstance(result[0], NoRecall)
    assert not any(isinstance(p, EpisodicPercept) for p in result)


def test_episodic_empty_cues_returns_norecall() -> None:
    sensor = EpisodicSensor([_trace("t1", hours_ago=1, what="李超问了部署")])
    result = sensor.perceive([], NOW)
    assert len(result) == 1 and isinstance(result[0], NoRecall)


# ---------- SemanticSensor ----------


def test_semantic_default_only_currently_valid() -> None:
    """默认只返回当前有效集：valid_to 已填的旧 claim 被过滤。"""
    sensor = SemanticSensor(
        [
            _claim("c-new", "用户住在长沙大道嘉宇盛世华章", valid_to=None),
            _claim(
                "c-old",
                "用户住在北京",
                valid_from=NOW - timedelta(days=90),
                valid_to=NOW - timedelta(days=1),
            ),
        ]
    )
    result = sensor.perceive(["用户住在"], NOW)
    ids = [p.claim.id for p in result if isinstance(p, SemanticPercept)]
    assert ids == ["c-new"]
    # A1：provenance 取自 claim.sources，confidence 取自 claim.confidence
    p = result[0]
    assert isinstance(p, SemanticPercept)
    assert p.provenance == "trace:t1"
    assert p.confidence == pytest.approx(0.9)


def test_semantic_as_of_point_in_time() -> None:
    """as_of 显式传入 → point-in-time 查询：被取代的历史 claim 可查回。"""
    old = _claim(
        "c-old",
        "用户住在北京",
        valid_from=NOW - timedelta(days=90),
        valid_to=NOW - timedelta(days=1),
    )
    new = _claim("c-new", "用户住在长沙大道嘉宇盛世华章", valid_to=None)
    future = _claim(
        "c-future", "用户将搬去深圳", valid_from=NOW + timedelta(days=1), valid_to=None
    )
    sensor = SemanticSensor([old, new, future])
    # 默认：旧 claim（已失效）与未来 claim（未生效）都不出现
    default_ids = {
        p.claim.id for p in sensor.perceive(["用户", "住", "搬"], NOW) if isinstance(p, SemanticPercept)
    }
    assert default_ids == {"c-new"}
    # as_of=两天前：旧 claim 有效，可查回（Zep 式"上周二我们相信什么"）
    as_of = NOW - timedelta(days=2)
    hist = sensor.perceive(["用户住在"], NOW, as_of=as_of)
    hist_ids = {p.claim.id for p in hist if isinstance(p, SemanticPercept)}
    assert "c-old" in hist_ids


def test_semantic_cue_miss_returns_norecall() -> None:
    sensor = SemanticSensor([_claim("c1", "用户喜欢喝茶")])
    result = sensor.perceive(["量子计算"], NOW)
    assert len(result) == 1 and isinstance(result[0], NoRecall)


def test_semantic_low_confidence_fail_closed() -> None:
    """C2：confidence=0.2 的 claim 即使被 cue 命中 → 显式 NoRecall。

    fail-closed：不上报，也绝不"降级"为文本上报——结果里不许出现
    任何 SemanticPercept，更不许出现裸文本。
    """
    sensor = SemanticSensor([_claim("c-low", "用户喜欢喝茶", confidence=0.2)])
    result = sensor.perceive(["喝茶"], NOW)
    assert len(result) == 1
    assert isinstance(result[0], NoRecall)
    assert not any(isinstance(p, SemanticPercept) for p in result)
    assert not any(isinstance(p, str) for p in result)


# ---------- RelationSensor ----------


def test_relation_sensor_hits_person() -> None:
    sensor = RelationSensor({"李超": "用户本人，长沙", "peter": "协作的另一个 Muse 实例"})
    result = sensor.perceive(["李超"], NOW)
    assert len(result) == 1
    p = result[0]
    assert isinstance(p, RelationPercept)
    assert p.person == "李超"
    assert p.context == "用户本人，长沙"
    assert p.provenance.strip() != ""
    assert p.confidence == pytest.approx(1.0)


def test_relation_sensor_cue_miss_returns_norecall() -> None:
    sensor = RelationSensor({"李超": "用户本人"})
    result = sensor.perceive(["奥特曼"], NOW)
    assert len(result) == 1 and isinstance(result[0], NoRecall)


# ---------- MemorySensorRegistry ----------


def test_registry_perceive_all_groups_by_sensor() -> None:
    registry = MemorySensorRegistry()
    registry.register("episodic", EpisodicSensor([_trace("t1", 1, "李超问了部署")]))
    registry.register("semantic", SemanticSensor([_claim("c1", "用户住在长沙")]))
    registry.register("relation", RelationSensor({"李超": "用户本人"}))
    out = registry.perceive_all(["李超", "部署", "长沙"], NOW)
    assert set(out.keys()) == {"episodic", "semantic", "relation"}
    assert isinstance(out["episodic"][0], EpisodicPercept)
    assert isinstance(out["semantic"][0], SemanticPercept)
    assert isinstance(out["relation"][0], RelationPercept)


def test_registry_keeps_norecall_honest() -> None:
    """sensor 明确说"我不记得" → registry 原样透出 NoRecall。"""
    registry = MemorySensorRegistry()
    registry.register("episodic", EpisodicSensor([_trace("t1", 1, "李超问了部署")]))
    out = registry.perceive_all(["量子计算"], NOW)
    assert len(out["episodic"]) == 1
    assert isinstance(out["episodic"][0], NoRecall)


class _LeakySensor:
    """故意不做 C2 门控的 sensor：验证 registry 是第二道门（协议合规的真实 sensor，非 mock）。"""

    def __init__(self, items: list) -> None:
        self._items = items

    def perceive(self, cues: list[str], now: datetime, limit: int = 5) -> list:
        return list(self._items)


def test_registry_gates_low_confidence_second_door() -> None:
    """registry 门控：confidence=0.2 的 percept 即使 sensor 漏报也被过滤（不上报）。"""
    leaky = _LeakySensor(
        [
            SemanticPercept(
                claim=_claim("c-low", "用户喜欢喝茶", confidence=0.2),
                provenance="trace:t9",
                confidence=0.2,
            )
        ]
    )
    registry = MemorySensorRegistry()
    registry.register("leaky", leaky)
    out = registry.perceive_all(["喝茶"], NOW)
    assert out["leaky"] == []


def test_registry_max_percepts_truncation() -> None:
    """token 预算：超 max_percepts 时全局按 confidence 从高到低截断。"""
    traces = [_trace(f"t{i}", hours_ago=i, what="李超问了部署") for i in range(6)]
    registry = MemorySensorRegistry(max_percepts=3)
    registry.register("episodic", EpisodicSensor(traces))
    out = registry.perceive_all(["部署"], NOW)
    percepts = out["episodic"]
    assert len(percepts) == 3
    # 置信度 = recency_score，最新的三条 trace 置信度最高
    assert [p.trace.id for p in percepts] == ["t0", "t1", "t2"]
    assert [p.confidence for p in percepts] == sorted(
        [p.confidence for p in percepts], reverse=True
    )


def test_registry_register_duplicate_raises() -> None:
    registry = MemorySensorRegistry()
    registry.register("episodic", EpisodicSensor([]))
    with pytest.raises(ValueError):
        registry.register("episodic", EpisodicSensor([]))


def test_registry_register_invalid_sensor_raises() -> None:
    registry = MemorySensorRegistry()
    with pytest.raises(TypeError):
        registry.register("bad", object())


def test_registry_max_percepts_must_be_positive() -> None:
    with pytest.raises(ValueError):
        MemorySensorRegistry(max_percepts=0)


def test_percept_requires_provenance_and_confidence() -> None:
    """C2：percept 的 provenance 非空、confidence 必须在 0..1。"""
    trace = _trace("t1", 1, "李超问了部署")
    with pytest.raises(ValueError):
        EpisodicPercept(
            trace=trace, recency_score=0.5, provenance="  ", confidence=0.5
        )
    claim = _claim("c1", "用户住在长沙", confidence=0.9)
    with pytest.raises(ValueError):
        SemanticPercept(claim=claim, provenance="trace:t1", confidence=1.5)
    with pytest.raises(ValueError):
        NoRecall(reason="  ")
