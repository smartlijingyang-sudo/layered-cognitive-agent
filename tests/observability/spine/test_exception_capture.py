"""异常归一化 SSOT 端到端测试 —— 任何异常都进 sidecar。

覆盖：
- ``exc_to_record`` 字段齐全(boundary / exception_class /
  exception_message / traceback_text / source_location / call_frames /
  cause_chain / run_id / trace_id / err_kind)
- ``cause_chain`` 去重 + 跳过 self
- ``ExceptionRecord.asdict()`` 含 legacy alias (exc_type / reason)
  + 新 ``err_kind``
- traceback by-frame cap: 64 帧截断,栈顶优先,栈底优先丢
- ``emit_exception_caught`` 是唯一 SSOT emitter —— 与 FileSink
  端到端:任何异常事件必然落 ``<sha256>.json`` sidecar,
  主 ledger 用 ``{execution_point, offloaded: <digest>}`` 占位符。
- lifecycle / decorator 两条路径都用 ``exc_to_record`` 归一化
  (SSOT 工厂唯一)。
"""

from __future__ import annotations

import json
import ssl
from datetime import datetime, timezone
from pathlib import Path

from lca.contracts.observability import (
    ErrKind,
    ExceptionRecord,
    exc_to_record,
)
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
        err_kind=ErrKind.INTERNAL,
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
        "err_kind",
        "run_id",
        "trace_id",
        # legacy alias
        "exc_type",
        "reason",
    ):
        assert key in d, f"missing {key}"
    assert d["exc_type"] == "ValueError"
    assert d["reason"] == "m"
    assert d["err_kind"] == "internal"


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


def test_emit_exception_caught_has_single_definition() -> None:
    """``def emit_exception_caught`` exists only in the SSOT emitter module."""
    repo_root = Path(__file__).resolve().parents[3]
    hits: list[str] = []
    for path in (repo_root / "lca").rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.lstrip().startswith("def emit_exception_caught"):
                hits.append(f"{path.relative_to(repo_root)}:{lineno}")
    assert len(hits) == 1, hits
    assert hits[0].startswith("lca/infrastructure/observability/spine/exception_emit.py:")


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

    # sidecar 必有(占位符 schema 包含 ``sidecar`` —— 可读文件名)
    digest = main["offloaded"]
    sidecar_name = main["sidecar"]
    sidecar = run_dir / sidecar_name
    assert sidecar.exists(), "sidecar must exist for any exception event"
    assert sidecar_name.startswith(digest[:8])
    assert sidecar_name.endswith("-ValueError.json")

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
        "err_kind",
        "exc_type",
        "reason",
    ):
        assert key in d, f"wrap path missing {key}"
    assert d["exception_class"] == "KeyError"
    assert "wrap path" in d["traceback_text"]
    assert d["err_kind"] == "internal"


# ── err_kind 分类 ───────────────────────────────────────────────────────────────


def test_exc_to_record_classifies_ssl_want_read_as_ssl() -> None:
    """``ssl.SSLWantReadError`` 由 classify_exception 标为 SSL。

    模拟 LLM 流式 SSL 帧被掐的场景(SSLWantReadError 是 SSL 三件套里
    最常见的非致命读帧信号 —— 在 python 3.12+ 升级 path 中可能移到
    ``_ssl`` 子模块或被重命名,所以另走 name 启发式兜底)。
    """
    ssl_exc: ssl.SSLWantReadError = ssl.SSLWantReadError()
    rec = exc_to_record(ssl_exc, boundary="x")
    assert rec.err_kind is ErrKind.SSL
    assert rec.asdict()["err_kind"] == "ssl"


def test_exc_to_record_classifies_cancellation() -> None:
    import asyncio as _asyncio

    try:
        raise _asyncio.CancelledError()
    except BaseException as exc:
        rec = exc_to_record(exc, boundary="x")
    assert rec.err_kind is ErrKind.CANCELLED


def test_classify_exception_business_builtin_maps_to_internal() -> None:
    """业务 ValueError / KeyError 等 OTel 表外 builtin 异常 → INTERNAL。

    这部分异常在本仓出现意味着 LCA 代码的意外,不是外部网络/取消/SANDBOX,
    应走 triage 路径(读 traceback 而非 retry)。
    """
    from lca.contracts.observability.exception_capture import classify_exception

    assert classify_exception(ValueError("x")) is ErrKind.INTERNAL
    assert classify_exception(KeyError("k")) is ErrKind.INTERNAL
    assert classify_exception(LookupError("l")) is ErrKind.INTERNAL


def test_classify_exception_unknown_when_no_signal() -> None:
    """非 builtin / 非已知名 = UNKNOWN 兜底。"""

    from lca.contracts.observability.exception_capture import classify_exception

    class _Unknown(BaseException):
        pass

    assert classify_exception(_Unknown("x")) is ErrKind.UNKNOWN


# ── by-frame cap ────────────────────────────────────────────────────────────────


def test_exc_to_record_caps_traceback_text_by_frame_budget() -> None:
    """框架数 > frame_budget → traceback_text 只输出最近 N 帧。"""

    def _deep(depth: int) -> None:
        if depth == 0:
            raise ValueError("deep")
        _deep(depth - 1)

    try:
        _deep(120)
    except ValueError as exc:
        full_rec = exc_to_record(exc, boundary="x", frame_budget=128)
        capped_rec = exc_to_record(exc, boundary="x", frame_budget=8)

    # 完整栈应远大于 8 帧
    assert len(full_rec.call_frames) > 8
    # call_frames 永远保留全栈 —— 只是 traceback_text 被截
    assert len(capped_rec.call_frames) == len(full_rec.call_frames)
    # 截过的 traceback_text 明显比完整短
    assert len(capped_rec.traceback_text) < len(full_rec.traceback_text)
    # 截过的文本仍含栈顶(抛出处 _deep)和 ValueError 行
    assert "_deep" in capped_rec.traceback_text
    assert "ValueError: deep" in capped_rec.traceback_text


def test_exc_to_record_frame_budget_does_not_drop_raising_site() -> None:
    """栈底优先丢 —— 抛出处(最末帧)必须在 traceback_text 中。"""

    def _raise() -> None:
        raise ValueError("raising site")

    def _middle() -> None:
        _raise()

    try:
        _middle()
    except ValueError as exc:
        rec = exc_to_record(exc, boundary="x", frame_budget=4)
    # 当前测试文件的栈顶帧 + _raise 栈底 都应在;被截掉的应是栈中间其他模块
    assert "ValueError: raising site" in rec.traceback_text
    # source_location 总是最末帧 —— 即 _raise 的现场
    assert rec.source_location is not None
    assert rec.source_location.function == "_raise"


# ── lifecycle 路径 emit 端到端 ──────────────────────────────────────────────────


def test_lifecycle_path_emit_includes_err_kind(tmp_path: Path) -> None:
    """lifecycle 走 emit_exception_caught → spine JSONL 含 err_kind。

    注意:SSLWantReadError 不带 __traceback__,traceback_text 较小,
    payload 序列化后 **未必** 越过 FileSink 4 KiB 阈值 → 可能无 sidecar。
    err_kind 仍以 JSON 行(主 ledger 或 offload)记录。本测试用 call_stack
    触发一个 frame 充足的 ValueError,这样 file_sink 必然 offload 到 sidecar。
    """
    from lca.harness.declarative.compile.instrument_wrap import (
        set_active_spine_accessor,
    )

    run_id = "r_lifecycle"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    file_sink = FileSink(run_dir, run_id=run_id)
    spine = EventSpine(sinks=[file_sink], run_id=run_id)
    previous = set_active_spine_accessor(lambda: spine)

    try:
        # 多帧 ValueError —— 保证 traceback_text 长度令 payload > 4 KiB
        def _a() -> None:
            def _b() -> None:
                raise ssl.SSLWantReadError()

            _b()

        try:
            _a()
        except BaseException as exc:
            rec = exc_to_record(exc, boundary="lifecycle.execute")
            emit_exception_caught(rec)
    finally:
        set_active_spine_accessor(previous)

    spine.close()
    file_sink.close()

    # 主 ledger 必有,且 on-load payload 含 err_kind = "ssl"
    payload = None
    # exceptions.jsonl 里含完整 payload,主 ledger 是 placeholder
    exc_path = run_dir / f"{run_id}.exceptions.jsonl"
    exc_lines = exc_path.read_text().splitlines()
    for line in exc_lines:
        parsed = json.loads(line)
        if parsed.get("execution_point") == "exception.caught":
            payload = parsed["payload"]
            break
    assert payload is not None, "exception.caught event not found in exceptions.jsonl"
    assert payload["err_kind"] == "ssl"
    assert payload["exception_class"] == "SSLWantReadError"
    # call_frames 至少含 _a / _b 帧
    frame_funcs = [f["function"] for f in payload["call_frames"]]
    assert "_b" in frame_funcs
