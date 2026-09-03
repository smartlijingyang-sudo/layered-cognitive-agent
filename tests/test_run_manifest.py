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
        # ADR-0096 I7: derived view holds journal seq, not hard event_id.
        terminal_event_seq=7,
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


# ── ADR-0068 §决策二:plan_ref 顶层字段(round-trip + 顶层位置) ──────
#
# run_3b30e4c5b10e 时 manifest 顶层无 plan_ref 字段,profile_snapshot.plan_ref=""
# (session 没字段)。修复后:
# - RunManifest.plan_ref 是顶层 dataclass 字段,不是 extra 子键
# - to_dict() 输出顶层 "plan_ref"
# - from_dict() 读顶层 plan_ref,缺失时 fallback "" (兼容旧 manifest)
# - round-trip 必须稳定
# ─────────────────────────────────────────────────────────────────


def test_manifest_plan_ref_top_level_field() -> None:
    """plan_ref 是 RunManifest 顶层字段,不在 extra 里。

    旧实现把 plan_ref 藏在 extra.plan_ref(没存)或 profile_snapshot.plan_ref=""
    (没字段),reader 必须多一层 grep。修复后 manifest 顶层直接有 plan_ref,
    ``cat manifest.json | jq .plan_ref`` 一行拿到。
    """
    m = RunManifest(run_id="r1", plan_ref="bc461bdcb30179e1")
    payload = m.to_dict()
    # 顶层字段,不嵌套
    assert "plan_ref" in payload
    assert payload["plan_ref"] == "bc461bdcb30179e1"
    assert payload.get("extra", {}).get("plan_ref") is None, (
        "plan_ref must be a top-level field, not in extra"
    )


def test_manifest_plan_ref_round_trip_with_real_compiled_run_plan_ref() -> None:
    """用真 compiled_run_plan_ref(16-hex)做 round-trip。

    锁住 plan_ref 的事实格式:16 hex chars(declarative 路径)或 mode
    fingerprint(solo 路径,同样 16 hex)。任何 reader 都按 16-hex 解析。
    """
    from lca.harness.plan import compiled_run_plan_ref
    from lca.harness.profile.plan_compiler import compile_plan
    from lca.harness.profile.resolve import resolve_profile

    profile = resolve_profile("profiles/web-standard.yaml")
    plan = compile_plan(profile)
    expected_ref = compiled_run_plan_ref(plan)

    # 真实 plan_ref 长度恰好 16 hex
    assert len(expected_ref) == 16
    assert all(c in "0123456789abcdef" for c in expected_ref)

    m = RunManifest(run_id="r", plan_ref=expected_ref)
    restored = RunManifest.from_dict(m.to_dict())
    assert restored.plan_ref == expected_ref
    assert restored.plan_ref == m.plan_ref


def test_manifest_plan_ref_empty_string_round_trip_compat() -> None:
    """plan_ref="" round-trip 必须稳定,旧 manifest(无该字段)也能读出 ""。

    兼容老 manifest.json:没 plan_ref 顶层字段时,from_dict 应输出 "" 而不抛错。
    这是删 RunManifest.plan_ref 字段的兼容护栏(虽 ADR-0068 要求顶层)。
    """
    m = RunManifest(run_id="r", plan_ref="")
    restored = RunManifest.from_dict(m.to_dict())
    assert restored.plan_ref == ""

    # 模拟旧 manifest(没有 plan_ref 字段)
    old_payload = {"schema": "lca.run_manifest/1", "run_id": "r"}
    restored_old = RunManifest.from_dict(old_payload)
    assert restored_old.plan_ref == "", "old manifest without plan_ref must default to empty string"


def test_manifest_plan_ref_position_locked_between_run_id_and_terminal_event_seq() -> None:
    """plan_ref 字段位置在 run_id 后、terminal_event_seq 前(SSOT 字段顺序)。

    字段顺序在 dataclass(frozen=True) 是确定的;reader 按位置解析时不能错位。
    """
    m = RunManifest(run_id="r", plan_ref="p")
    payload = m.to_dict()
    keys = list(payload.keys())
    run_id_idx = keys.index("run_id")
    plan_ref_idx = keys.index("plan_ref")
    terminal_seq_idx = keys.index("terminal_event_seq")
    assert run_id_idx < plan_ref_idx < terminal_seq_idx, (
        f"plan_ref must be between run_id and terminal_event_seq, got keys order: {keys}"
    )
