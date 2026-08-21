"""Evidence contract shape —— Protocol 运行时校验(ADR-0065 PR-2)。

确认 Classification / RetentionClass / EvidenceRef / EvidenceReceipt / EvidencePolicy
/ EvidenceStore 形状稳定,新加字段必须显式更新本测试。
"""

from __future__ import annotations

import time

from lca.contracts.observability.evidence import (
    Classification,
    EvidenceIntegrityError,
    EvidencePolicy,
    EvidenceReceipt,
    EvidenceRef,
    EvidenceStore,
    RetentionClass,
)


def test_classification_enum_values_stable() -> None:
    assert Classification.PUBLIC.value == "public"
    assert Classification.INTERNAL.value == "internal"
    assert Classification.RESTRICTED.value == "restricted"
    assert Classification.CONFIDENTIAL.value == "confidential"
    # 闭集:枚举成员数 == 4(新增需要 ADR)
    assert len(Classification) == 4


def test_retention_class_enum_values_stable() -> None:
    assert RetentionClass.RUN_DEFAULT.value == "run-default"
    assert RetentionClass.SESSION.value == "session"
    assert RetentionClass.LONG.value == "long"
    assert RetentionClass.PERMANENT.value == "permanent"
    assert len(RetentionClass) == 4


def test_evidence_ref_round_trip() -> None:
    ref = EvidenceRef(
        algorithm="sha256",
        digest="a" * 64,
        media_type="text/plain",
        byte_length=42,
        classification=Classification.INTERNAL,
        retention=RetentionClass.LONG,
        locator="traces/evidence/sha256/aaaa",
    )
    payload = ref.to_dict()
    restored = EvidenceRef.from_dict(payload)
    assert restored == ref


def test_evidence_ref_default_values() -> None:
    ref = EvidenceRef()
    assert ref.algorithm == "sha256"
    assert ref.digest == ""
    assert ref.media_type == "application/octet-stream"
    assert ref.byte_length == 0
    assert ref.classification == Classification.INTERNAL
    assert ref.retention == RetentionClass.RUN_DEFAULT
    assert ref.locator == ""


def test_evidence_receipt_is_frozen_and_slotted() -> None:
    receipt = EvidenceReceipt(
        ref=EvidenceRef(digest="b" * 64),
        prepared_at=time.time(),
        prepared_by="test",
        content_sha256="b" * 64,
    )
    # frozen dataclass —— 字段赋值抛错
    try:
        receipt.prepared_by = "hacked"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("EvidenceReceipt should be frozen")


def test_protocols_are_runtime_checkable() -> None:
    # Protocol 必须可被 isinstance 检查 —— seam + provider wiring 依赖
    assert hasattr(EvidenceStore, "prepare")
    assert hasattr(EvidenceStore, "get")
    assert hasattr(EvidenceStore, "contains")
    assert hasattr(EvidenceStore, "sweep_orphan")

    assert hasattr(EvidencePolicy, "classify")
    assert hasattr(EvidencePolicy, "retention")
    assert hasattr(EvidencePolicy, "should_inline")


def test_evidence_integrity_error_is_runtime_error() -> None:
    err = EvidenceIntegrityError("test")
    assert isinstance(err, RuntimeError)
    assert str(err) == "test"


def test_evidence_ref_to_dict_keys_stable() -> None:
    """to_dict 字段集是公开契约;新增字段必须同步 from_dict。"""
    ref = EvidenceRef(digest="c" * 64)
    keys = set(ref.to_dict().keys())
    expected = {
        "algorithm",
        "digest",
        "media_type",
        "byte_length",
        "classification",
        "retention",
        "locator",
    }
    assert keys == expected
