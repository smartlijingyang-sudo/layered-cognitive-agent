"""ADR-0277 Phase 6：双时间线（bitemporal）验收测试（ADR §4 A2）。

场景"用户改地址"（Zep 式 point-in-time）：
  t0：addr-1 入库（用户住在长沙大道）；
  t1：用户说新地址，LinkDecider.reconcile(addr-2, [addr-1], now=t1)；
  t2：默认查询只返回当前有效集 addr-2，as_of=t0+1小时 可查回 addr-1。

说明：cues 用 ["地址", "住在"]——落地版 _cue_hits 是双向子串匹配，
纯 "地址" 命中不了任一 claim（会触发 C2 fail-closed 返回 NoRecall），
因此补 "住在" 让 cues 真实命中，双时间线过滤的验收意图不变。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lca.cognition.memory.consolidation import LinkDecider
from lca.cognition.memory.sensors import NoRecall, SemanticPercept, SemanticSensor
from lca.cognition.memory.types import SemanticClaim

_SH = timezone(timedelta(hours=8))  # Asia/Shanghai

T0 = datetime(2026, 9, 29, 10, 0, tzinfo=_SH)  # addr-1 入库
T1 = T0 + timedelta(hours=2)  # 用户说新地址
T2 = T1 + timedelta(hours=2)  # 查询时刻

CUES = ["地址", "住在"]


def _addr1() -> SemanticClaim:
    """t0 入库的旧地址断言。"""
    return SemanticClaim(
        id="addr-1",
        claim="用户住在长沙大道",
        confidence=0.9,
        sources=("trace-1",),
        valid_from=T0,
        valid_to=None,
        supersedes=None,
    )


def _addr2() -> SemanticClaim:
    """t1 用户说的新地址断言。"""
    return SemanticClaim(
        id="addr-2",
        claim="用户住在雨花区",
        confidence=0.85,
        sources=("trace-2",),
        valid_from=None,
        valid_to=None,
        supersedes=None,
    )


def _reconcile() -> tuple[SemanticClaim, object]:
    """在 t1 对账，返回 (原 addr-1 对象, LinkResult)。"""
    addr1 = _addr1()
    result = LinkDecider().reconcile(_addr2(), [addr1], now=T1)
    return addr1, result


def test_conflict_retires_old_claim_with_valid_to() -> None:
    """冲突：旧 claim 被填 valid_to=t1（不删除），原 id 保留。"""
    _, result = _reconcile()
    retired = result.retired_claim
    assert retired is not None
    assert retired.id == "addr-1"
    assert retired.valid_to == T1
    # 新 claim 接替：supersedes 链 + 生效时间
    assert result.new_claim.id == "addr-2"
    assert result.new_claim.supersedes == "addr-1"
    assert result.new_claim.valid_from == T1
    assert result.outcome.effect == "superseded"


def test_original_claim_object_not_deleted() -> None:
    """旧 claim 对象本身未被删除：原变量仍可访问、字段完整、valid_to 未动。"""
    addr1, result = _reconcile()
    # replace 产出新对象，原对象保持入库时的样子
    assert result.retired_claim is not addr1
    assert addr1.id == "addr-1"
    assert addr1.claim == "用户住在长沙大道"
    assert addr1.confidence == 0.9
    assert addr1.sources == ("trace-1",)
    assert addr1.valid_from == T0
    assert addr1.valid_to is None
    assert addr1.supersedes is None


def test_consolidation_record_audit() -> None:
    """每次 reconcile 产出 ConsolidationRecord：decision == link，rationale 非空。"""
    _, result = _reconcile()
    record = result.outcome.record
    assert record.decision == "link"
    assert record.rationale.strip() != ""
    assert record.target_id == "addr-2"


def test_default_perceive_returns_current_set_only() -> None:
    """默认查询（as_of=None）只返回当前有效集：addr-2，addr-1 不出现。"""
    _, result = _reconcile()
    sensor = SemanticSensor([result.retired_claim, result.new_claim])
    hits = sensor.perceive(cues=CUES, now=T2)
    assert all(isinstance(p, SemanticPercept) for p in hits)
    ids = [p.claim.id for p in hits]  # type: ignore[union-attr]
    assert ids == ["addr-2"]


def test_as_of_point_in_time_recovers_old_claim() -> None:
    """as_of=t0+1小时（Zep 式"上周二我们相信什么"）：查回 addr-1。"""
    _, result = _reconcile()
    sensor = SemanticSensor([result.retired_claim, result.new_claim])
    hits = sensor.perceive(cues=CUES, now=T2, as_of=T0 + timedelta(hours=1))
    assert all(isinstance(p, SemanticPercept) for p in hits)
    ids = [p.claim.id for p in hits]  # type: ignore[union-attr]
    assert ids == ["addr-1"]
    # 查回的是带退休标记的历史版本（valid_to=t1），语义完整
    claim = hits[0].claim  # type: ignore[union-attr]
    assert claim.valid_to == T1
    assert claim.claim == "用户住在长沙大道"


def test_future_valid_from_invisible_before_start() -> None:
    """边界：valid_from 在未来的 claim，在 as_of 早于 valid_from 时不可见。"""
    future = SemanticClaim(
        id="addr-3",
        claim="用户住在天心区",
        confidence=0.8,
        sources=("trace-3",),
        valid_from=T2 + timedelta(days=1),
        valid_to=None,
        supersedes=None,
    )
    sensor = SemanticSensor([future])
    early = sensor.perceive(cues=CUES, now=T2, as_of=T2)
    assert len(early) == 1 and isinstance(early[0], NoRecall)
    late = sensor.perceive(
        cues=CUES, now=T2 + timedelta(days=2), as_of=T2 + timedelta(days=2)
    )
    assert all(isinstance(p, SemanticPercept) for p in late)
    assert [p.claim.id for p in late] == ["addr-3"]  # type: ignore[union-attr]
