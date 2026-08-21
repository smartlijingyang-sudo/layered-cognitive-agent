"""RunManifest 测试(ADR-0065 PR-6)。

- to_dict / from_dict round-trip 稳定
- materializer_default_version 不抛错
- evidence_integrity 状态枚举完整
- IntegrityState 闭集
"""

from __future__ import annotations

from lca.contracts.observability.run_manifest import (
    IntegrityState,
    ManifestEvidence,
    RunManifest,
)


def test_manifest_round_trip() -> None:
    m = RunManifest(
        run_id="run_a",
        terminal_event_id="evt_t",
        ledger_high_watermark=42,
        ledger_summary="sha256:abc",
        materializer_version="0.1.0",
        evidence_integrity=(
            ManifestEvidence(
                ref_digest="d" * 64,
                ref_algorithm="sha256",
                state=IntegrityState.OK,
            ),
        ),
        started_at=1.0,
        closed_at=2.0,
        pricing_ref="lca.cost/v1",
        extra={"foo": "bar"},
    )
    payload = m.to_dict()
    restored = RunManifest.from_dict(payload)
    assert restored == m


def test_manifest_minimal_round_trip() -> None:
    m = RunManifest(run_id="r")
    restored = RunManifest.from_dict(m.to_dict())
    assert restored == m


def test_manifest_schema_locked() -> None:
    m = RunManifest()
    assert m.schema == "lca.run_manifest/1"


def test_integrity_state_enum_is_closed() -> None:
    members = set(IntegrityState)
    assert IntegrityState.OK in members
    assert IntegrityState.MISSING in members
    assert IntegrityState.DIGEST_MISMATCH in members
    assert IntegrityState.UNKNOWN in members
    assert len(members) == 4


def test_manifest_evidence_default_values() -> None:
    ei = ManifestEvidence(ref_digest="d", ref_algorithm="sha256", state=IntegrityState.OK)
    assert ei.detail == ""


def test_materializer_default_version_returns_string() -> None:
    v = RunManifest.materializer_default_version()
    assert isinstance(v, str)
    assert v != ""
