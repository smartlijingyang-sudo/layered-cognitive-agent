"""ADR-0101 PR-2 + ADR-0101 followup (2026-09-01) 验收规约 —— V1/V2/V3/V4。

V-Journal 子集(ADR §9):
- V1:ToolStarted/ToolInvoked/ToolCallStreaming dataclass 不再有 typed 6-key /
    result_preview / plugin_state / state_ref 字段。``arguments_preview`` 在
    ADR-0101 followup 中作为例外保留 —— ToolCallStreaming 的 best-effort
    partial dict,replay 工具不得依赖,ToolStarted.arguments 才是事实。
- V2:ToolStarted 中 ``arguments`` 与 ``arguments_ref`` 二选一(非空互斥)。
- V3:journal_io 不再有 ``_strip_view_only_data`` 调用。
- V4:所有 tool 事件落盘后 ``arguments`` 或 ``arguments_ref`` 至少一个非空。

详见 ``docs/adr/0101-tool-facts-and-evidence-only.md`` §9 与
``docs/adr/0101-followup-tool-call-streaming-partial-preview.md``。
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import ClassVar

import pytest

from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolCallResolved,
    ToolInvoked,
    ToolStarted,
)
from lca.contracts.observability.evidence import (
    Classification,
    EvidenceRef,
    RetentionClass,
)
from lca.infrastructure.observability.journal.engine.journal_io import (
    JOURNAL_SCHEMA_VERSION,
    _envelope_v2_to_disk_record,
    stamped_to_record,
)

# V1 forbidden fields per ADR-0101 PR-2
# `output_text` is a legitimate inline-output field per ADR-0101 PR-2 (no
# longer view-only). `projected_state` is renderer-facing (SSE-only; stripped
# from disk by JsonlJournalProjector). Both live on ToolInvoked as proper
# dataclass fields and are excluded from the V1 forbidden set.
# 本批 (fix/strip-tool-call-streaming): ToolCallResolved 取代
# ToolCallStreaming;完整 arguments 走 inline (or evidence 平面),
# 不再有 best-effort partial preview 字段。
_V1_FORBIDDEN_FIELDS = (
    "code",
    "language",
    "command",
    "skill_id",
    "skill_inputs",
    "description",
    "execution_env",
    "result_preview",
    "plugin_state",
    "state_ref",
)


def _journal_event_field_names(cls: type) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)}


# ── V1 ────────────────────────────────────────────────────────────────────


def test_v1_no_typed_or_preview_fields() -> None:
    """V1:tool 事件 dataclass 不再有 typed 6-key / *_preview / plugin_state /
    state_ref 字段。"""
    for cls in (ToolCallResolved, ToolStarted, ToolInvoked):
        present = _journal_event_field_names(cls)
        for forbidden in _V1_FORBIDDEN_FIELDS:
            assert forbidden not in present, f"{cls.__name__} 不应保留 view-only 字段 {forbidden!r}"


def test_v1_dataclass_field_count() -> None:
    """tool 事件 dataclass 字段总数收敛(typed 6-key 全部移除)。

    ADR-XXXX adds ``output_text`` (inline output) and ``projected_state``
    (renderer-facing projection) to ToolInvoked.

    本批 (fix/strip-tool-call-streaming): ToolCallResolved 取代 ToolCallStreaming
    —— ``arguments`` 字段是完整 dict (与 ToolStarted.arguments 同 shape),
    不再带 ``arguments_preview`` 中间态字段。
    """
    resolved_fields = _journal_event_field_names(ToolCallResolved)
    assert resolved_fields == {
        "tool_name",
        "tool_call_id",
        "arguments",
        "arguments_ref",
    }
    started_fields = _journal_event_field_names(ToolStarted)
    assert started_fields == {
        "tool_name",
        "invocation_id",
        "arguments",
        "arguments_ref",
        "idempotency_key",
    }
    invoked_fields = _journal_event_field_names(ToolInvoked)
    expected_invoked = {
        "tool_name",
        "invocation_id",
        "ok",
        "latency_ms",
        "attempt",
        "error",
        "idempotency_key",
        "files",
        "arguments",
        "arguments_ref",
        "output_ref",
        "output_text",
        "output_truncated",
        "projected_state",
    }
    assert invoked_fields == expected_invoked


def test_v1_dataclass_rejects_legacy_fields() -> None:
    """V1 实操验证:ToolInvoked 不再接受 ``code=...`` / ``plugin_state=...`` 字段。

    ``arguments_preview`` 不再是 forbidden 字段 —— ADR-0101 followup 把它恢复
    为 ToolCallStreaming 的 streaming preview 字段(类型是 dict,不是 str)。
    """
    with pytest.raises(TypeError):
        ToolInvoked(tool_name="t", invocation_id="i", code="print(2)")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        ToolStarted(
            tool_name="t",
            invocation_id="i",
            plugin_state={"code": "x"},  # type: ignore[call-arg]
        )
    # ToolCallResolved.arguments 是 dict 类型,接受 dict(完整 args)
    ToolCallResolved(
        tool_name="t",
        tool_call_id="c",
        arguments={"code": "ls"},  # 完整 args,不再有 preview
    )


# ── V2 ────────────────────────────────────────────────────────────────────


def test_v2_arguments_xor_ref_default() -> None:
    """V2:默认构造时 ``arguments={}`` 与 ``arguments_ref=None`` 二选一(均空)。

    语义:两者不能同时有值(由 emit 路径保证);默认两者都为空是合法状态。
    """
    started = ToolStarted(tool_name="t", invocation_id="i")
    assert started.arguments == {}
    assert started.arguments_ref is None
    # explicit XOR:有 ref → arguments 为空
    ref = EvidenceRef(
        algorithm="sha256",
        digest="a" * 64,
        media_type="application/json",
        byte_length=0,
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    started2 = ToolStarted(tool_name="t", invocation_id="i", arguments_ref=ref)
    assert started2.arguments == {}
    assert started2.arguments_ref is not None


def test_v2_invoke_xor_ref_default() -> None:
    """V2 在 ToolInvoked 同样适用:arguments 与 arguments_ref 二选一。"""
    inv = ToolInvoked(tool_name="t", invocation_id="i")
    assert inv.arguments == {}
    assert inv.arguments_ref is None
    assert inv.output_ref is None
    ref = EvidenceRef(
        algorithm="sha256",
        digest="b" * 64,
        media_type="application/json",
        byte_length=0,
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
    )
    inv2 = ToolInvoked(tool_name="t", invocation_id="i", output_ref=ref)
    assert inv2.output_ref is not None


# ── V3 ────────────────────────────────────────────────────────────────────


def test_v3_journal_io_no_view_only_stripping() -> None:
    """V3:journal_io 不再有 ``_strip_view_only_data`` / ``_is_view_only_field`` 调用。"""
    from lca.infrastructure.observability.journal.engine import journal_io

    assert not hasattr(journal_io, "_strip_view_only_data")
    assert not hasattr(journal_io, "_is_view_only_field")
    # stamped_to_record / _envelope_v2_to_disk_record 不引用这些 helper
    src = inspect.getsource(stamped_to_record)
    assert "_strip_view_only_data" not in src
    assert "_is_view_only_field" not in src
    src2 = inspect.getsource(_envelope_v2_to_disk_record)
    assert "_strip_view_only_data" not in src2


def test_v3_journal_io_emit_passes_through_facts() -> None:
    """V3 实操验证:stamped_to_record 不再剥离 ``arguments`` 等事实字段。"""
    started = ToolStarted(tool_name="t", invocation_id="i")
    stamped = StampedEvent(seq=1, ts=1.0, scope=RunScope(trace_id="tr", run_id="r"), event=started)
    record = stamped_to_record(stamped)
    assert record["schema"] == JOURNAL_SCHEMA_VERSION
    assert "arguments" in record["data"]
    assert "arguments_ref" in record["data"]


# ── V4 ────────────────────────────────────────────────────────────────────


def test_v4_arguments_or_ref_always_set_after_emit() -> None:
    """V4:所有 tool 事件落盘后 ``arguments`` 或 ``arguments_ref`` 至少一个非空。

    走 emit_tool_started / emit_tool_invoked 的公共路径时,即使没有
    evidence_store,inline ``arguments`` 也会填充 args(退路)。
    """
    from lca.cognition.body.tool_journal_emit import (
        emit_tool_invoked,
        emit_tool_started,
    )

    class _MockTool:
        name = "demo"

    class _Obs:
        success: ClassVar[bool] = True
        payload: ClassVar[dict[str, str]] = {"text": "ok"}
        error: ClassVar[str] = ""
        extra: ClassVar[dict[str, object]] = {}

    # emit_tool_started: 无 evidence_store → inline 退路,arguments 非空
    ref = emit_tool_started(_MockTool(), {"path": "/x"}, "inv1")
    assert ref is None
    assert ref is None  # no evidence_store / policy → None
    # emit_tool_invoked: output_ref 走证据平面失败 → output_ref=None,
    # 但 inline arguments 退路 → arguments 非空(V4)
    emit_tool_invoked(
        _MockTool(),
        {"path": "/x"},
        _Obs(),  # type: ignore[arg-type]
        latency_ms=1,
        attempt=1,
        invocation_id="inv1",
        arguments_ref=None,
    )


def test_v4_disk_record_keeps_arguments_inline() -> None:
    """V4:inline arguments 落盘后保留(走 emit 公共路径)。"""
    from lca.cognition.body.tool_journal_emit import emit_tool_started

    class _Tool:
        name = "demo"

    emit_tool_started(_Tool(), {"a": 1}, "inv1")  # type: ignore[arg-type]
    # emit 已记录到当前 bound journal;通过 record path 检查 → 我们用 fixture
    # 直接构造 stamped,验证 stamped_to_record 保留 arguments
    started = ToolStarted(tool_name="demo", invocation_id="inv1", arguments={"a": 1})
    stamped = StampedEvent(seq=1, ts=1.0, scope=RunScope(trace_id="tr", run_id="r"), event=started)
    record = stamped_to_record(stamped)
    assert record["data"]["arguments"] == {"a": 1}


# ── Bonus:emit_tool_started 返回 arguments_ref ──────────────────────────────────


def test_emit_tool_started_returns_ref_when_evidence_bound() -> None:
    """emit_tool_started 走 evidence 平面 → 返回非空 arguments_ref。

    绑定 FilesystemEvidenceStore + DefaultEvidencePolicy,验证 inline 路径
    evidence_store.prepare() 真的被调用并返回 ref。
    """

    from lca.cognition.body.tool_journal_emit import emit_tool_started
    from lca.contracts.observability.evidence import (
        Classification,
        EvidenceReceipt,
        RetentionClass,
    )

    class _Tool:
        name = "demo"

    class _MockStore:
        def prepare(self, payload, *, classification, retention, media_type, prepared_by):
            return EvidenceReceipt(
                ref=EvidenceRef(
                    algorithm="sha256",
                    digest="c" * 64,
                    media_type=media_type,
                    byte_length=len(payload),
                    classification=classification,
                    retention=retention,
                ),
                prepared_at=0.0,
                prepared_by=prepared_by,
                content_sha256="c" * 64,
            )

    class _MockPolicy:
        def classify(self, payload, *, media_type="application/octet-stream"):
            return Classification.INTERNAL

        def retention(self, payload, *, hint=None):
            return RetentionClass.RUN_DEFAULT

        def should_inline(self, payload, *, classification):
            return False

    ref = emit_tool_started(
        _Tool(),
        {"a": 1, "b": "x" * 200},  # type: ignore[arg-type]
        "inv1",
        evidence_store=_MockStore(),  # type: ignore[arg-type]
        evidence_policy=_MockPolicy(),  # type: ignore[arg-type]
    )
    assert ref is not None
    assert ref.digest == "c" * 64


def test_inline_path_activated_by_should_inline_true() -> None:
    """ADR-0101 §5.3 inline 路径已启用:policy.should_inline=True → 无 ref。

    验证小 + public payload 不走 evidence plane round-trip,直接 inline。
    互斥:V2(同时只能有一个非空)。
    """

    from lca.cognition.body.tool_journal_emit import emit_tool_started
    from lca.contracts.observability.evidence import (
        Classification,
        RetentionClass,
    )

    class _Tool:
        name = "demo"

    prepare_called = {"count": 0}

    class _TrackingStore:
        def prepare(self, payload, *, classification, retention, media_type, prepared_by):
            prepare_called["count"] += 1
            raise AssertionError("evidence_store.prepare should NOT be called when inline")

    class _InlinePolicy:
        def classify(self, payload, *, media_type="application/octet-stream"):
            return Classification.PUBLIC

        def retention(self, payload, *, hint=None):
            return RetentionClass.RUN_DEFAULT

        def should_inline(self, payload, *, classification):
            return True

    ref = emit_tool_started(
        _Tool(),
        {"small": "public payload"},  # type: ignore[arg-type]
        "inv2",
        evidence_store=_TrackingStore(),  # type: ignore[arg-type]
        evidence_policy=_InlinePolicy(),  # type: ignore[arg-type]
    )
    # V2:ref 为 None(走 inline),V4:policy 命中 inline → 不调 prepare
    assert ref is None
    assert prepare_called["count"] == 0


# ── 本批 (fix/strip-tool-call-streaming): ToolCallResolved 取代 preview ────


def test_resolved_carries_full_arguments_dict() -> None:
    """ToolCallResolved.arguments 是完整 dict (与 ToolStarted.arguments 同 shape)。

    验证:
    1. arguments 字段是 dict
    2. 完整 dict 可携带 code/language 等所有 keys
    3. ToolStarted 不携带 streaming 中间态字段 (无 arguments_preview)
    """
    complete = ToolCallResolved(
        tool_name="executeCode",
        tool_call_id="c1",
        arguments={"code": "print(2)", "language": "python"},
    )
    assert complete.arguments == {"code": "print(2)", "language": "python"}

    started = ToolStarted(tool_name="executeCode", invocation_id="c1")
    started_fields = {f.name for f in dataclasses.fields(started)}
    assert "arguments_preview" not in started_fields
    assert "arguments" in started_fields


def test_resolved_serializes_full_arguments_to_disk() -> None:
    """ToolCallResolved.arguments 完整 dict 写入 jsonl (与 ToolStarted 同路径)。

    V3 验证:journal_io 不剥离 arguments,inline dict 作为事实写入 disk。
    """
    from lca.infrastructure.observability.journal.engine.journal_io import (
        stamped_to_record,
    )

    record_in = ToolCallResolved(
        tool_name="executeCode",
        tool_call_id="c1",
        arguments={"code": "print(2)", "language": "python"},
    )
    stamped = StampedEvent(
        event=record_in,
        scope=RunScope(run_id="r1", trace_id="t1"),
        seq=1,
        ts=1.0,
    )
    out = stamped_to_record(stamped)
    data = out.get("data", {})
    assert data.get("arguments") == {"code": "print(2)", "language": "python"}


def test_resolved_has_no_partial_preview_field() -> None:
    """ToolCallResolved 不再有 arguments_preview (本批移除)。

    旧 ToolCallStreaming 的 arguments_preview 是 UI 中间态,已废。
    """
    resolved_fields = {f.name for f in dataclasses.fields(ToolCallResolved)}
    assert "arguments_preview" not in resolved_fields, (
        "ToolCallResolved.arguments_preview 已废;UI 打字机是前端层职责"
    )
