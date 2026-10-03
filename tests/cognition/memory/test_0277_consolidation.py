"""ADR-0277 Phase 5 测试：remember 显式 consolidation 四决策。

覆盖 ADR §4 A3（低 salience 在 encode 阶段被丢弃）与 A5（每次决策都有
ConsolidationRecord，decision 四选一、rationale 非空），以及冲突/重复/无关
对账、decay 只降权不删除、LayaDecider fail-closed 与低 confidence 回退。

全部断言真实行为；Laya 用本文件内的 FakeEngine，不依赖真模型。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from lca.cognition.memory.consolidation import (
    ConsolidationContext,
    ConsolidationOutcome,
    DecayPolicy,
    EncodeGate,
    LayaDecider,
    LinkDecider,
    LinkResult,
    RuleDecider,
    RuleSchemaExtractor,
)
from lca.cognition.memory.types import (
    ConsolidationRecord,
    EpisodicTrace,
    SemanticClaim,
)

_NOW = datetime(2026, 10, 3, 9, 0, 0)


def _trace(
    id: str = "ep-1",
    what: str = "用户在长沙出差",
    salience: float = 0.8,
    days_ago: float = 1.0,
    who: tuple[str, ...] = ("李超",),
) -> EpisodicTrace:
    when = _NOW - timedelta(days=days_ago)
    return EpisodicTrace(
        id=id, when=when, ingested_at=when, who=who, what=what, salience=salience
    )


def _claim(
    id: str = "cl-1",
    claim: str = "用户喜欢深色模式",
    valid_to: datetime | None = None,
    supersedes: str | None = None,
) -> SemanticClaim:
    return SemanticClaim(
        id=id,
        claim=claim,
        confidence=0.9,
        sources=("ep-1",),
        valid_from=_NOW - timedelta(days=10),
        valid_to=valid_to,
        supersedes=supersedes,
    )


def _ctx(*claims: SemanticClaim) -> ConsolidationContext:
    return ConsolidationContext(existing_claims=list(claims), now=_NOW)


# ---------------------------------------------------------------------------
# encode：A3 低 salience 被丢弃
# ---------------------------------------------------------------------------


def test_encode_drops_low_salience() -> None:
    """A3：低 salience 候选在 encode 阶段被丢弃（阈值以下无写入）。"""
    outcome = EncodeGate(salience_threshold=0.3).evaluate(_trace(salience=0.1))
    assert outcome.effect == "dropped"
    assert outcome.record.decision == "encode"
    assert outcome.record.target_id == "ep-1"
    # rationale 写明阈值与实际值
    assert "0.100" in outcome.record.rationale
    assert "0.300" in outcome.record.rationale


def test_encode_keeps_at_threshold() -> None:
    """边界：salience 恰等于阈值时允许编码（>=）。"""
    outcome = EncodeGate(salience_threshold=0.3).evaluate(_trace(salience=0.3))
    assert outcome.effect == "kept"
    assert outcome.record.decision == "encode"


def test_encode_keeps_high_salience() -> None:
    outcome = EncodeGate().evaluate(_trace(salience=0.9))
    assert outcome.effect == "kept"


# ---------------------------------------------------------------------------
# link：冲突 / 重复 / 无关
# ---------------------------------------------------------------------------


def test_link_conflict_retires_old_claim() -> None:
    """冲突：旧 claim 填 valid_to 失效（不删除），新 claim supersedes 指向旧 id。"""
    old = _claim(id="cl-old", claim="用户喜欢深色模式")
    new = _claim(id="cl-new", claim="用户喜欢浅色模式")
    result = LinkDecider().reconcile(new, [old], _NOW)

    assert isinstance(result, LinkResult)
    assert result.outcome.effect == "superseded"
    assert result.outcome.record.decision == "link"
    # 旧 claim 失效但可查回（C4 双时间线）
    assert result.retired_claim is not None
    assert result.retired_claim.id == "cl-old"
    assert result.retired_claim.valid_to == _NOW
    assert result.retired_claim.is_valid_at(_NOW - timedelta(days=1))
    assert not result.retired_claim.is_valid_at(_NOW + timedelta(days=1))
    # 新 claim 的 supersedes 指向旧 id
    assert result.new_claim.supersedes == "cl-old"
    assert result.new_claim.id == "cl-new"


def test_link_duplicate_merges() -> None:
    """重复：归一化文本相同 → merged，rationale 写明合并到哪个 id。"""
    old = _claim(id="cl-old", claim="用户喜欢深色模式")
    new = _claim(id="cl-new", claim="用户喜欢深色模式。")  # 标点差异归一化后相同
    result = LinkDecider().reconcile(new, [old], _NOW)
    assert result.outcome.effect == "merged"
    assert result.outcome.record.decision == "link"
    assert "cl-old" in result.outcome.record.rationale
    assert result.retired_claim is None


def test_link_unrelated_adds() -> None:
    """无关：与现有 claim 主题词无重叠 → added。"""
    old = _claim(id="cl-old", claim="用户喜欢深色模式")
    new = _claim(id="cl-new", claim="今天长沙天气晴朗")
    result = LinkDecider().reconcile(new, [old], _NOW)
    assert result.outcome.effect == "added"
    assert result.new_claim.id == "cl-new"
    assert result.retired_claim is None


def test_link_skips_already_retired_claims() -> None:
    """已失效的旧 claim 不再参与对账（C4：历史只读）。"""
    retired_old = _claim(
        id="cl-old", claim="用户喜欢深色模式", valid_to=_NOW - timedelta(days=1)
    )
    new = _claim(id="cl-new", claim="用户喜欢浅色模式")
    result = LinkDecider().reconcile(new, [retired_old], _NOW)
    assert result.outcome.effect == "added"


def test_link_conflict_uses_replace_not_mutation() -> None:
    """非丢失式：reconcile 不修改传入的旧 claim 对象（frozen + replace）。"""
    old = _claim(id="cl-old", claim="用户喜欢深色模式")
    new = _claim(id="cl-new", claim="用户喜欢浅色模式")
    LinkDecider().reconcile(new, [old], _NOW)
    assert old.valid_to is None  # 传入对象未被改动


# ---------------------------------------------------------------------------
# A5：每次决策都有 ConsolidationRecord，decision 四选一、rationale 非空
# ---------------------------------------------------------------------------


def test_every_decision_has_audit_record() -> None:
    """A5：encode/link/decay/schema 每次决策产出 record，decision 四选一、rationale 非空。"""
    dense_traces = [
        _trace(id=f"ep-{i}", what="用户每周三关注部署", days_ago=float(i * 2))
        for i in range(3)
    ]
    outcomes: list[ConsolidationOutcome] = [
        EncodeGate().evaluate(_trace(salience=0.9)),  # encode/kept
        EncodeGate().evaluate(_trace(salience=0.1)),  # encode/dropped
        LinkDecider()
        .reconcile(
            _claim(id="cl-new", claim="用户喜欢浅色模式"),
            [_claim(id="cl-old", claim="用户喜欢深色模式")],
            _NOW,
        )
        .outcome,  # link/superseded
        RuleDecider().decide(
            _trace(salience=0.8, days_ago=60.0), _ctx()
        ),  # decay/decayed
        RuleSchemaExtractor().extract(dense_traces, _NOW)[0][1],  # schema/extracted
    ]
    decisions = {o.record.decision for o in outcomes}
    assert decisions == {"encode", "link", "decay", "schema"}
    for outcome in outcomes:
        assert outcome.record.decision in ("encode", "link", "decay", "schema")
        assert outcome.record.rationale.strip() != ""


def test_outcome_rejects_illegal_decision() -> None:
    """decision 非四选一时构造即抛 ValueError（Literal 只做静态检查）。"""
    record = ConsolidationRecord(
        decision="bogus",  # type: ignore[arg-type]
        target_id="ep-1",
        rationale="非法 decision",
    )
    with pytest.raises(ValueError, match="四选一"):
        ConsolidationOutcome(record=record, effect="kept")  # type: ignore[arg-type]


def test_record_rejects_empty_rationale() -> None:
    """rationale 为空时 ConsolidationRecord 构造即抛（C5）。"""
    with pytest.raises(ValueError):
        ConsolidationRecord(decision="encode", target_id="ep-1", rationale="  ")


# ---------------------------------------------------------------------------
# decay：只降权不删除
# ---------------------------------------------------------------------------


def test_decay_halves_per_half_life() -> None:
    """Ebbinghaus 式：60 天 / 半衰期 30 天 → salience 降为 1/4。"""
    policy = DecayPolicy(half_life_days=30.0)
    trace = _trace(salience=0.8, days_ago=60.0)
    assert policy.decayed_salience(trace, _NOW) == pytest.approx(0.2)


def test_decay_only_downweights_never_deletes() -> None:
    """decay 只降权不删除：原 trace 对象 salience 不变，下限 0.05。"""
    policy = DecayPolicy(half_life_days=30.0)
    trace = _trace(salience=0.8, days_ago=365.0)
    decayed = policy.decayed_salience(trace, _NOW)
    assert decayed >= 0.05  # 下限
    assert decayed < trace.salience  # 降权
    assert trace.salience == 0.8  # 原对象未被改动（frozen）


def test_needs_decay_false_for_fresh_trace() -> None:
    """新 trace（age≈0）不需要 decay。"""
    assert not DecayPolicy().needs_decay(_trace(days_ago=0.0), _NOW)


def test_needs_decay_false_at_floor() -> None:
    """已触底（salience=下限）的 trace 不再衰减。"""
    assert not DecayPolicy().needs_decay(
        _trace(salience=0.05, days_ago=365.0), _NOW
    )


def test_needs_decay_true_for_old_trace() -> None:
    assert DecayPolicy().needs_decay(_trace(salience=0.8, days_ago=60.0), _NOW)


# ---------------------------------------------------------------------------
# RuleDecider 编排：encode → link → decay
# ---------------------------------------------------------------------------


def test_rule_decider_short_circuits_on_drop() -> None:
    """encode 丢弃则短路，不跑 link/decay。"""
    outcome = RuleDecider().decide(_trace(salience=0.1), _ctx(_claim()))
    assert outcome.effect == "dropped"
    assert outcome.record.decision == "encode"


def test_rule_decider_link_then_decay() -> None:
    """link 仅 added 时继续评估 decay：老 trace → decayed。"""
    outcome = RuleDecider().decide(
        _trace(salience=0.8, days_ago=60.0, what="用户在长沙出差"),
        _ctx(_claim(id="cl-old", claim="服务器磁盘空间不足")),
    )
    assert outcome.effect == "decayed"
    assert outcome.record.decision == "decay"
    assert "只降权不删除" in outcome.record.rationale


def test_rule_decider_link_added_without_decay() -> None:
    """新 trace（age=0，无衰减空间）+ 无关 claim → added（decay 无需跑）。"""
    outcome = RuleDecider().decide(
        _trace(salience=0.8, days_ago=0.0, what="用户在长沙出差"),
        _ctx(_claim(id="cl-old", claim="服务器磁盘空间不足")),
    )
    assert outcome.effect == "added"
    assert outcome.record.decision == "link"


def test_rule_decider_conflict_wins_over_decay() -> None:
    """link 产出 superseded 时直接返回（审计不丢失），即使 trace 很老也不跑 decay。"""
    outcome = RuleDecider().decide(
        _trace(salience=0.8, days_ago=365.0, what="用户喜欢浅色模式"),
        _ctx(_claim(id="cl-old", claim="用户喜欢深色模式")),
    )
    assert outcome.effect == "superseded"
    assert outcome.record.decision == "link"


# ---------------------------------------------------------------------------
# schema：Letta sleep-time 提炼（规则版占位）
# ---------------------------------------------------------------------------


def test_schema_extracts_repeated_topic() -> None:
    """同一 who 在 7 天窗口内出现 3 次相似 what → 提炼一条 claim。"""
    traces = [
        _trace(id="ep-1", what="用户每周三关注部署", days_ago=0.0),
        _trace(id="ep-2", what="用户每周三关注部署", days_ago=2.0),
        _trace(id="ep-3", what="用户每周三关注部署", days_ago=5.0),
    ]
    results = RuleSchemaExtractor().extract(traces, _NOW)
    assert len(results) == 1
    claim, outcome = results[0]
    assert claim.confidence == 0.6
    assert set(claim.sources) == {"ep-1", "ep-2", "ep-3"}  # 窗口内 3 条 trace 的 id
    assert claim.valid_to is None
    assert outcome.effect == "extracted"
    assert outcome.record.decision == "schema"
    assert outcome.record.target_id == claim.id
    assert claim.id.startswith("schema-")


def test_schema_ignores_sparse_mentions() -> None:
    """不足 3 次 → 不提炼。"""
    traces = [
        _trace(id="ep-1", what="用户每周三关注部署", days_ago=0.0),
        _trace(id="ep-2", what="用户每周三关注部署", days_ago=2.0),
    ]
    assert RuleSchemaExtractor().extract(traces, _NOW) == []


def test_schema_ignores_out_of_window() -> None:
    """3 次但跨度超过 7 天 → 不提炼。"""
    traces = [
        _trace(id="ep-1", what="用户每周三关注部署", days_ago=0.0),
        _trace(id="ep-2", what="用户每周三关注部署", days_ago=5.0),
        _trace(id="ep-3", what="用户每周三关注部署", days_ago=11.0),
    ]
    assert RuleSchemaExtractor().extract(traces, _NOW) == []


def test_schema_groups_by_who() -> None:
    """不同 who 的相同 what 不合并提炼。"""
    traces = [
        _trace(id="ep-1", what="用户每周三关注部署", days_ago=0.0, who=("李超",)),
        _trace(id="ep-2", what="用户每周三关注部署", days_ago=1.0, who=("李超",)),
        _trace(id="ep-3", what="用户每周三关注部署", days_ago=2.0, who=("peter",)),
    ]
    assert RuleSchemaExtractor().extract(traces, _NOW) == []


# ---------------------------------------------------------------------------
# LayaDecider：fail-closed + 低 confidence 回退（FakeEngine，不依赖真模型）
# ---------------------------------------------------------------------------


class _FakeDecision:
    """LayaDecision 的测试替身。"""

    def __init__(self, decision: str, confidence: float, raw: dict) -> None:
        self.decision = decision
        self.confidence = confidence
        self.raw = raw


class _FakeEngine:
    """LayaScoreEngine 的测试替身：按 schema 分发预设脚本。"""

    def __init__(self, available: bool = True, handler=None) -> None:
        self._available = available
        self._handler = handler or (lambda state, schema: _FakeDecision("noop", 1.0, {}))
        self.calls: list[tuple[dict, dict]] = []

    def is_available(self) -> bool:
        return self._available

    def decide(self, state: dict, schema: dict) -> _FakeDecision:
        self.calls.append((state, schema))
        return self._handler(state, schema)


def _noul_handler(worth: bool, confidence: float = 0.9):
    def _handle(state: dict, schema: dict) -> _FakeDecision:
        if "worth_extracting" in schema:
            return _FakeDecision("noul", confidence, {"worth_extracting": worth})
        return _FakeDecision("choice", 0.9, {"resolution": "keep_both"})

    return _handle


def test_laya_unavailable_raises_without_engine() -> None:
    """未注入 engine → decide() 抛 RuntimeError（fail-closed）。"""
    with pytest.raises(RuntimeError, match="fail-closed"):
        LayaDecider().decide(_trace(), _ctx())


def test_laya_unavailable_raises_when_not_available() -> None:
    """is_available()=False → decide() 抛 RuntimeError（fail-closed）。"""
    engine = _FakeEngine(available=False)
    with pytest.raises(RuntimeError, match="fail-closed"):
        LayaDecider(engine=engine).decide(_trace(), _ctx())
    assert engine.calls == []  # 不可用时一次也不调模型


def test_laya_noul_rejects_worthless() -> None:
    """noul 判定不值得提炼 → dropped（decision=encode）。"""
    engine = _FakeEngine(handler=_noul_handler(worth=False))
    outcome = LayaDecider(engine=engine).decide(_trace(), _ctx())
    assert outcome.effect == "dropped"
    assert outcome.record.decision == "encode"
    assert "noul" in outcome.record.rationale


def test_laya_choice_supersede() -> None:
    """choice 高 confidence 判 supersede → 旧 claim 失效，新 claim supersedes 指向旧 id。"""
    old = _claim(id="cl-old", claim="用户喜欢深色模式")

    def _handle(state: dict, schema: dict) -> _FakeDecision:
        if "worth_extracting" in schema:
            return _FakeDecision("noul", 0.95, {"worth_extracting": True})
        assert state["new_claim"] == "用户喜欢浅色模式"
        assert state["old_claim"] == "用户喜欢深色模式"
        assert schema == {"resolution": "enum[supersede,merge,keep_both]"}
        return _FakeDecision("choice", 0.9, {"resolution": "supersede"})

    decider = LayaDecider(engine=_FakeEngine(handler=_handle))
    outcome = decider.decide(
        _trace(what="用户喜欢浅色模式"), _ctx(old)
    )
    assert outcome.effect == "superseded"
    assert outcome.record.decision == "link"
    assert "Laya choice" in outcome.record.rationale
    assert "cl-old" in outcome.record.rationale


def test_laya_choice_merge() -> None:
    """choice 判 merge → merged。"""

    def _handle(state: dict, schema: dict) -> _FakeDecision:
        if "worth_extracting" in schema:
            return _FakeDecision("noul", 0.95, {"worth_extracting": True})
        return _FakeDecision("choice", 0.9, {"resolution": "merge"})

    outcome = LayaDecider(engine=_FakeEngine(handler=_handle)).decide(
        _trace(what="用户喜欢深色模式"), _ctx(_claim())
    )
    assert outcome.effect == "merged"


def test_laya_low_confidence_falls_back_to_rule() -> None:
    """choice confidence < 0.6 → 显式回退 RuleDecider（rationale 为规则文本）。"""
    old = _claim(id="cl-old", claim="用户喜欢深色模式")

    def _handle(state: dict, schema: dict) -> _FakeDecision:
        if "worth_extracting" in schema:
            return _FakeDecision("noul", 0.95, {"worth_extracting": True})
        return _FakeDecision("choice", 0.5, {"resolution": "keep_both"})

    outcome = LayaDecider(engine=_FakeEngine(handler=_handle)).decide(
        _trace(what="用户喜欢浅色模式"), _ctx(old)
    )
    assert outcome.effect == "superseded"  # 回退到规则：冲突启发式同样判冲突
    assert "Laya choice" not in outcome.record.rationale  # 规则文本，非 Laya 判定
    assert "规则判定冲突" in outcome.record.rationale


def test_laya_keep_both_adds() -> None:
    """choice 全票 keep_both → added。"""
    outcome = LayaDecider(engine=_FakeEngine(handler=_noul_handler(worth=True))).decide(
        _trace(what="用户在长沙出差"), _ctx(_claim())
    )
    assert outcome.effect == "added"
    assert "keep_both" in outcome.record.rationale


def test_laya_skips_retired_claims_in_choice() -> None:
    """choice 只对有效旧 claim 跑，已失效的不送模型。"""
    retired = _claim(
        id="cl-old", claim="用户喜欢深色模式", valid_to=_NOW - timedelta(days=1)
    )
    engine = _FakeEngine(handler=_noul_handler(worth=True))
    outcome = LayaDecider(engine=engine).decide(
        _trace(what="用户喜欢浅色模式"), _ctx(retired)
    )
    assert outcome.effect == "added"
    choice_calls = [c for c in engine.calls if "resolution" in c[1]]
    assert choice_calls == []


def test_replace_keeps_old_object_intact() -> None:
    """dataclasses.replace 产生新实例：被取代的旧 claim 原对象 valid_to 仍为 None。"""
    old = _claim(id="cl-old", claim="用户喜欢深色模式")
    retired = replace(old, valid_to=_NOW)
    assert old.valid_to is None
    assert retired.valid_to == _NOW
    assert retired.id == old.id
