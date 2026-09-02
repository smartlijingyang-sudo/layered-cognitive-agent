"""异常归一化 SSOT 端到端测试 —— 任何异常都进 sidecar。

覆盖：
- ``exc_to_record`` 字段齐全(boundary / exception_class /
  exception_message / traceback_text / source_location / call_frames /
  cause_chain / run_id / trace_id)
- ``cause_chain`` 去重 + 跳过 self
- ``ExceptionRecord.asdict()`` 含 legacy alias (exc_type / reason)
- ``emit_exception_caught`` 是唯一 SSOT emitter —— 与 FileSink
  端到端:任何异常事件必然落 ``<sha256>.json`` sidecar,
  主 ledger 用 ``{execution_point, offloaded: <digest>}`` 占位符。
- lifecycle / decorator 两条路径都用 ``exc_to_record`` 归一化
  (SSOT 工厂唯一)。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lca.contracts.observability import ExceptionRecord, exc_to_record
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine
from lca.infrastructure.observability.spine.exception_emit import (
    emit_exception_caught,
)
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink


def _make_rec(**overrides: object) -> EventRecord:
    base: dict[str, object] = {
        "execution_point": "brain.think.start",
        "channel": "fact",
        "span_id": "01HM",
        "parent_span_id": None,
        "sequence": 1,
        "epoch": 1,
        "causality_id": "ca",
        "outcome": None,
        "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        "when_corrected": datetime(2026, 9, 1, 12, 0, 0, 100000, tzinfo=timezone.utc),
        "prev_event_hash": None,
        "run_id": "r1",
        "step_id": "s1",
        "payload": {"x": 1},
    }
    base.update(overrides)
    return EventRecord(**base)  # type: ignore[arg-type]


# ── exc_to_record 字段契约 ─────────────────────────────────────────────────────────


def test_exc_to_record_fields_complete() -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        rec = exc_to_record(exc, boundary="lifecycle.execute", run_id="r1")

    assert rec.boundary == "lifecycle.execute"
    assert rec.exception_class == "ValueError"
    assert rec.exception_message == "boom"
    assert "ValueError: boom" in rec.traceback_text
    # traceback_text 至少包含 caller 帧 —— 精确到行
    assert "test_exception_capture.py" in rec.traceback_text
    assert rec.source_location is not None
    assert rec.source_location.line > 0
    assert rec.source_location.function.endswith("test_exc_to_record_fields_complete")
    # call_frames 应包含本测试函数自身帧
    frames_files = [f.file for f in rec.call_frames]
    assert any("test_exception_capture.py" in f for f in frames_files)
    assert rec.run_id == "r1"
    assert rec.trace_id == ""
    # 当前没有 __cause__ / __context__,chain 为空
    assert rec.cause_chain == ()


def test_exc_to_record_dedups_cause_chain_and_skips_self() -> None:
    inner = ValueError("inner")
    try:
        raise RuntimeError("outer") from inner
    except RuntimeError as exc:
        rec = exc_to_record(exc, boundary="x")

    # __cause__ 应该是 ValueError(显式 from)
    assert "ValueError" in rec.cause_chain
    # 不应包含 self 类型
    assert "RuntimeError" not in rec.cause_chain


def test_exc_to_record_unicode_message_roundtrips() -> None:
    try:
        raise ValueError("异常: 错误信息 🔥")
    except ValueError as exc:
        rec = exc_to_record(exc, boundary="x")

    assert rec.exception_message == "异常: 错误信息 🔥"
    assert "异常: 错误信息 🔥" in rec.traceback_text


def test_exc_to_record_handles_missing_traceback() -> None:
    """``raise ValueError('x') from None`` 且 exc.__traceback__ 为 None 也不崩。"""

    exc = ValueError("constructed")
    # 构造但不 raise,__traceback__ 应为 None
    assert exc.__traceback__ is None
    rec = exc_to_record(exc, boundary="x")

    assert rec.source_location is None
    assert rec.call_frames == ()
    # 无 __traceback__ 时 format_exception 仍输出 "ValueError: constructed\n"
    assert "ValueError: constructed" in rec.traceback_text


# ── asdict 契约 + legacy alias ──────────────────────────────────────────────────


def test_asdict_contains_all_canonical_fields() -> None:
    rec = ExceptionRecord(
        boundary="x",
        exception_class="ValueError",
        exception_message="m",
        traceback_text="tb",
        source_location=None,
        call_frames=(),
        cause_chain=(),
        run_id="r1",
        trace_id="t1",
    )
    d = rec.asdict()
    for key in (
        "boundary",
        "exception_class",
        "exception_message",
        "traceback_text",
        "source_location",
        "call_frames",
        "cause_chain",
        "run_id",
        "trace_id",
        # legacy alias
        "exc_type",
        "reason",
    ):
        assert key in d, f"missing {key}"
    assert d["exc_type"] == "ValueError"
    assert d["reason"] == "m"


def test_extra_overrides_legacy_alias_but_not_canonical() -> None:
    """caller 通过 extra 注入反射增强字段;legacy alias 不被覆盖。"""
    import dataclasses

    rec = ExceptionRecord(
        boundary="x",
        exception_class="ValueError",
        exception_message="m",
        traceback_text="tb",
        source_location=None,
        call_frames=(),
        cause_chain=(),
        run_id="r1",
        trace_id="t1",
    )
    rec2 = dataclasses.replace(
        rec,
        extra={"locals_snapshot": {"pre": {"x": "1"}}, "signature_fingerprint": "abc"},
    )
    d = rec2.asdict()
    assert d["locals_snapshot"] == {"pre": {"x": "1"}}
    assert d["signature_fingerprint"] == "abc"
    # legacy alias 不变
    assert d["exc_type"] == "ValueError"
    assert d["reason"] == "m"


# ── emit_exception_caught 端到端：sidecar 必有 ──────────────────────────────────


def test_emit_exception_caught_writes_sidecar_for_any_exception(tmp_path: Path) -> None:
    """任何异常事件 payload size > 4 KiB → FileSink 自动 offload → sidecar 必有。"""
    from lca.harness.declarative.compile.instrument_wrap import (
        set_active_spine_accessor,
    )

    run_id = "r_exception"
    run_dir = tmp_path / "traces" / "runs" / run_id
    run_dir.mkdir(parents=True)

    file_sink = FileSink(run_dir, run_id=run_id)
    spine = EventSpine(sinks=[file_sink], run_id=run_id)

    previous = set_active_spine_accessor(lambda: spine)
    try:
        try:
            raise ValueError("any exception must produce sidecar")
        except ValueError as exc:
            record = exc_to_record(
                exc,
                boundary="lifecycle.execute",
                run_id=run_id,
                trace_id="trace_x",
            )
        emitted = emit_exception_caught(record)
        assert emitted is not None
    finally:
        set_active_spine_accessor(previous)

    spine.close()
    file_sink.close()

    # 主 ledger 引用 offload
    spine_path = run_dir / f"{run_id}.spine.jsonl"
    assert spine_path.exists()
    main_lines = spine_path.read_text().splitlines()
    assert len(main_lines) >= 1
    main = json.loads(main_lines[-1])
    assert main.get("execution_point") == "exception.caught"
    assert main.get("offloaded"), "main ledger must reference offloaded digest"

    # sidecar 必有
    digest = main["offloaded"]
    sidecar = run_dir / f"{digest}.json"
    assert sidecar.exists(), "sidecar must exist for any exception event"

    # sidecar payload 字段齐全
    sidecar_payload = json.loads(sidecar.read_text())
    for key in (
        "boundary",
        "exception_class",
        "exception_message",
        "traceback_text",
        "source_location",
        "call_frames",
        "cause_chain",
        "run_id",
        "trace_id",
    ):
        assert key in sidecar_payload["payload"], f"sidecar missing payload key {key}"
    p = sidecar_payload["payload"]
    assert p["exception_class"] == "ValueError"
    assert p["exception_message"] == "any exception must produce sidecar"
    assert "any exception must produce sidecar" in p["traceback_text"]
    assert p["boundary"] == "lifecycle.execute"
    assert p["run_id"] == run_id
    assert p["trace_id"] == "trace_x"


def test_emit_exception_caught_small_message_still_offloads_due_to_call_frames(
    tmp_path: Path,
) -> None:
    """即使 exception_message 短,call_frames + traceback_text 也让 payload 超 4 KiB。"""
    from lca.harness.declarative.compile.instrument_wrap import (
        set_active_spine_accessor,
    )

    run_id = "r_short"
    run_dir = tmp_path / "traces" / "runs" / run_id
    run_dir.mkdir(parents=True)

    file_sink = FileSink(run_dir, run_id=run_id)
    spine = EventSpine(sinks=[file_sink], run_id=run_id)

    previous = set_active_spine_accessor(lambda: spine)
    try:
        try:
            raise RuntimeError("x")
        except RuntimeError as exc:
            record = exc_to_record(exc, boundary="b", run_id=run_id)
        emit_exception_caught(record)
    finally:
        set_active_spine_accessor(previous)

    spine.close()
    file_sink.close()

    sidecars = [p for p in run_dir.glob("*.json") if p.name != f"{run_id}.spine.jsonl"]
    assert len(sidecars) == 1, "every exception event must offload to a sidecar"


# ── SSOT 工厂唯一性：decorator 路径也走 exc_to_record ────────────────────────────


def test_instrument_wrap_exception_payload_uses_ssot() -> None:
    """装饰器 ``_exception_payload`` 必须返回 ``exc_to_record(...).asdict()``。"""
    from lca.harness.declarative.compile.instrument_wrap import _exception_payload

    try:
        raise KeyError("wrap path")
    except KeyError as exc:
        d = _exception_payload(exc)

    # SSOT 字段齐全(包含 legacy alias)
    for key in (
        "boundary",
        "exception_class",
        "exception_message",
        "traceback_text",
        "source_location",
        "call_frames",
        "cause_chain",
        "exc_type",
        "reason",
    ):
        assert key in d, f"wrap path missing {key}"
    assert d["exception_class"] == "KeyError"
    assert "wrap path" in d["traceback_text"]
