"""ADR-0277 Phase 1 测试：typed 记忆对象构造 / 字段校验 / 双时间线查询。

全部断言真实行为，不 mock。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from lca.cognition.memory.types import (
    W_CUE,
    W_RECENCY,
    W_SALIENCE,
    W_SEMANTIC,
    ConsolidationRecord,
    EpisodicTrace,
    ProceduralRule,
    ScoredCandidate,
    SemanticClaim,
)

_NOW = datetime(2026, 10, 3, 8, 0, 0)


def _trace(**kwargs) -> EpisodicTrace:
    base = {
        "id": "ep-1",
        "when": _NOW - timedelta(days=2),
        "ingested_at": _NOW - timedelta(days=2),
        "who": ("李超",),
        "what": "用户在长沙雨花区确认国庆行程",
        "salience": 0.8,
    }
    base.update(kwargs)
    return EpisodicTrace(**base)


def _claim(**kwargs) -> SemanticClaim:
    base = {
        "id": "sm-1",
        "claim": "用户住长沙雨花区",
        "confidence": 0.9,
        "sources": ("ep-1",),
        "valid_from": _NOW - timedelta(days=30),
        "valid_to": None,
        "supersedes": None,
    }
    base.update(kwargs)
    return SemanticClaim(**base)


# ---------- 构造成功 ----------


def test_episodic_trace_builds():
    t = _trace()
    assert t.id == "ep-1"
    assert t.who == ("李超",)
    assert t.what.startswith("用户在长沙")
    assert t.salience == 0.8


def test_semantic_claim_builds_with_supersedes_chain():
    old = _claim(id="sm-0", valid_to=_NOW - timedelta(days=1))
    new = _claim(id="sm-1", supersedes="sm-0")
    assert new.supersedes == "sm-0"
    assert old.valid_to is not None  # 被取代的旧 claim 填 valid_to，不删除


def test_procedural_rule_builds():
    r = ProceduralRule(id="pr-1", trigger="用户说「整理发票」", action="打开发票 Dashboard", scope="全局")
    assert r.action == "打开发票 Dashboard"
    assert r.scope == "全局"


def test_consolidation_record_builds_all_decisions():
    for decision in ("encode", "link", "decay", "schema"):
        rec = ConsolidationRecord(decision=decision, target_id="sm-1", rationale="与旧 claim 冲突，旧 claim 标记失效")
        assert rec.decision == decision
        assert rec.rationale


def test_scored_candidate_builds_and_weights_sum_to_one():
    c = ScoredCandidate(
        item_id="sm-1",
        kind="semantic",
        semantic_sim=0.9,
        recency=0.5,
        salience=0.8,
        cue_match=0.7,
        score=round(
            W_SEMANTIC * 0.9 + W_RECENCY * 0.5 + W_SALIENCE * 0.8 + W_CUE * 0.7,
            6,
        ),
    )
    assert c.score == pytest.approx(W_SEMANTIC * 0.9 + W_RECENCY * 0.5 + W_SALIENCE * 0.8 + W_CUE * 0.7)
    assert W_SEMANTIC + W_SALIENCE + W_RECENCY + W_CUE == pytest.approx(1.0)


# ---------- 字段校验失败 ----------


def test_salience_out_of_range_raises():
    with pytest.raises(ValueError):
        _trace(salience=1.5)
    with pytest.raises(ValueError):
        _trace(salience=-0.1)


def test_confidence_out_of_range_raises():
    with pytest.raises(ValueError):
        _claim(confidence=2.0)


def test_empty_claim_raises():
    with pytest.raises(ValueError):
        _claim(claim="")
    with pytest.raises(ValueError):
        _claim(claim="   ")


def test_empty_what_raises():
    with pytest.raises(ValueError):
        _trace(what="")


def test_empty_action_raises():
    with pytest.raises(ValueError):
        ProceduralRule(id="pr-1", trigger="t", action="", scope="全局")


def test_empty_rationale_raises():
    with pytest.raises(ValueError):
        ConsolidationRecord(decision="encode", target_id="sm-1", rationale="")
    with pytest.raises(ValueError):
        ConsolidationRecord(decision="link", target_id="sm-1", rationale="   ")


def test_scored_candidate_component_out_of_range_raises():
    with pytest.raises(ValueError):
        ScoredCandidate(
            item_id="sm-1",
            kind="semantic",
            semantic_sim=1.2,  # 越界
            recency=0.5,
            salience=0.8,
            cue_match=0.7,
            score=0.7,
        )


# ---------- is_valid_at 双时间线 ----------


def test_is_valid_at_currently_valid():
    c = _claim(valid_from=_NOW - timedelta(days=30), valid_to=None)
    assert c.is_valid_at(_NOW) is True


def test_is_valid_at_expired():
    c = _claim(
        valid_from=_NOW - timedelta(days=30),
        valid_to=_NOW - timedelta(days=1),  # 昨天已失效
    )
    assert c.is_valid_at(_NOW) is False
    # 但历史时刻仍可查回（Zep 式 point-in-time）
    assert c.is_valid_at(_NOW - timedelta(days=10)) is True


def test_is_valid_at_future_effective():
    c = _claim(valid_from=_NOW + timedelta(days=1), valid_to=None)  # 明天才生效
    assert c.is_valid_at(_NOW) is False
    assert c.is_valid_at(_NOW + timedelta(days=2)) is True


def test_is_valid_at_open_valid_from():
    c = _claim(valid_from=None, valid_to=None)
    assert c.is_valid_at(_NOW) is True


# ---------- supersedes 链字段存在 ----------


def test_supersedes_chain_fields_present():
    new = _claim(supersedes="sm-0")
    assert hasattr(new, "supersedes") and hasattr(new, "valid_from") and hasattr(new, "valid_to")
    assert new.supersedes == "sm-0"
    assert new.valid_to is None  # 新 claim 当前有效
