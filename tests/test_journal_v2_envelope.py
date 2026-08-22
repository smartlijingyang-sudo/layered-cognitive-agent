"""JournalRecord v2 envelope round-trip + 字段约束(ADR-0065 §三 / PR-3)。

- schema 必填 "lca.journal/2"
- occurred_at vs committed_at 可表达不同时间(0065 §三)
- causation.parent_event_id + causation.links 非空可选
- descriptor.version / payload_schema_version 显式
- evidence: tuple[EvidenceRef, ...] 引用
- 不可变 slots + frozen
"""

from __future__ import annotations

import dataclasses
import time

from lca.contracts.models.observability.journal import (
    AgentRunStarted,
    Causation,
    DescriptorRef,
    JournalRecord,
    RunScope,
    StampedEvent,
    stamped_to_journal_record,
)
from lca.contracts.observability.evidence import (
    Classification,
    EvidenceRef,
    RetentionClass,
)
from lca.layer0_infra.observability.journal.serialization import (
    stamped_to_journal_record,
)


def test_causation_links_round_trip() -> None:
    """causation.links 表达非树形关联(重试 / 跨 run / 外部 trace)。"""
    jr = JournalRecord(
        causation=Causation(
            parent_event_id="evt_a",
            links=(
                {"kind": "external_trace", "external_trace_id": "trace_xyz"},
                {"kind": "retry_of", "event_id": "evt_prev"},
            ),
        )
    )
    payload = jr.to_dict()
    assert payload["causation"]["parent_event_id"] == "evt_a"
    assert len(payload["causation"]["links"]) == 2
    restored = JournalRecord.from_dict(payload)
    assert len(restored.causation.links) == 2


def test_evidence_refs_round_trip_v2() -> None:
    ref = EvidenceRef(
        digest="a" * 64,
        media_type="text/plain",
        byte_length=42,
        classification=Classification.INTERNAL,
        retention=RetentionClass.LONG,
    )
    jr = JournalRecord(evidence=(ref,))
    payload = jr.to_dict()
    assert payload["evidence"][0]["digest"] == "a" * 64
    restored = JournalRecord.from_dict(payload)
    assert restored.evidence[0] == ref


def test_journal_record_slots_prevent_attribute_addition() -> None:
    """slots 防意外字段(0065 §三 envelope 封闭)。

    Python 3.14 + dataclass(frozen=True, slots=True) 在赋值新字段时抛
    TypeError(super(type, obj) 内部异常),而不是 AttributeError;但只要赋值
    不成功,envelope 封闭性得到保证。
    """
    jr = JournalRecord()
    raised = False
    try:
        jr.custom_field = "boom"  # type: ignore[attr-defined]
    except (AttributeError, TypeError, dataclasses.FrozenInstanceError):
        raised = True
    assert raised, "slots/frozen must reject new attributes"


def test_journal_record_has_slots() -> None:
    """__slots__ 已声明 —— 杜绝 __dict__ 增长,envelope 字段集封闭。"""
    assert "__slots__" in JournalRecord.__dict__ or hasattr(
        JournalRecord, "__slots__"
    )


def test_schema_is_locked_to_v2() -> None:
    jr = JournalRecord()
    assert jr.schema == "lca.journal/2"


def test_round_trip_preserves_all_fields() -> None:
    jr = JournalRecord(
        event_id="evt_01J",
        run_id="run_01",
        run_seq=42,
        occurred_at=time.time(),
        committed_at=time.time() + 0.05,
        scope=RunScope(trace_id="trace_a", run_id="run_01", agent_role="researcher"),
        causation=Causation(parent_event_id="evt_prev", links=()),
        descriptor=DescriptorRef(type="LlmCallCompleted", version=2, payload_schema_version=2),
        data={"model": "test-model", "prompt_tokens": 100},
        evidence=(),
    )
    payload = jr.to_dict()
    restored = JournalRecord.from_dict(payload)
    assert restored == jr


def test_occurred_at_can_differ_from_committed_at() -> None:
    """L2 '提交先于观察' —— 源时间与写入时间显式可不同(0065 §三)。"""
    occurred = 1_000_000.0
    committed = 1_000_005.5
    jr = JournalRecord(occurred_at=occurred, committed_at=committed)
    assert jr.occurred_at != jr.committed_at
    restored = JournalRecord.from_dict(jr.to_dict())
    assert restored.occurred_at == occurred
    assert restored.committed_at == committed


def test_causation_with_links_removed() -> None:
    """Removed (superseded by test_causation_links_round_trip)."""
    pass


def test_descriptor_version_round_trip() -> None:
    """L4: descriptor.version 与 payload_schema_version 必须可序列化。"""
    d = DescriptorRef(type="X", version=3, payload_schema_version=2)
    payload = d.to_dict()
    assert payload == {"type": "X", "version": 3, "payload_schema_version": 2}
    restored = DescriptorRef.from_dict(payload)
    assert restored == d


def test_evidence_refs_round_trip_removed() -> None:
    """Removed (superseded by test_evidence_refs_round_trip_v2)."""
    pass


def test_journal_record_is_immutable() -> None:
    jr = JournalRecord()
    try:
        jr.run_seq = 999  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("JournalRecord must be frozen")


def test_stamped_to_journal_record_factory() -> None:
    """迁移期桥:旧 StampedEvent → 新 JournalRecord 不丢字段。"""
    payload = AgentRunStarted(agent_role="researcher", objective="test")
    stamped = StampedEvent(
        seq=1,
        ts=time.time(),
        scope=RunScope(trace_id="trace_a", run_id="run_01", agent_role="researcher"),
        event=payload,
        event_type="AgentRunStarted",
        data={"agent_role": "researcher", "objective": "test"},
        parent_seq=None,
    )
    jr = stamped_to_journal_record(
        stamped,
        event_id="evt_01",
        run_id="run_01",
        run_seq=1,
        occurred_at=stamped.ts,
        committed_at=stamped.ts,
        descriptor_version=2,
        payload_schema_version=2,
    )
    assert jr.schema == "lca.journal/2"
    assert jr.run_seq == 1
    assert jr.descriptor.type == "AgentRunStarted"
    assert jr.descriptor.version == 2
    assert jr.data == {"agent_role": "researcher", "objective": "test"}


def test_run_scope_round_trip_preserves_branded_ids() -> None:
    """RunScope brand-typed ID 字段经 dict 序列化后能正确重建。"""
    scope = RunScope(
        trace_id="trace_x",
        run_id="run_y",
        parent_run_id="run_parent",
        delegation_id="delegation_1",
        agent_role="lead",
        step=3,
    )
    jr = JournalRecord(scope=scope)
    payload = jr.to_dict()
    restored = JournalRecord.from_dict(payload)
    assert restored.scope.trace_id == scope.trace_id
    assert restored.scope.run_id == scope.run_id
    assert restored.scope.parent_run_id == scope.parent_run_id
    assert restored.scope.delegation_id == scope.delegation_id
    assert restored.scope.agent_role == scope.agent_role
    assert restored.scope.step == scope.step
