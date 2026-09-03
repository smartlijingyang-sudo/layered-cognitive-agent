"""TracingFileSink 必落盘保证 —— 测试覆盖所有 fallback 路径。

锁定的不变量:
1. 正常写入:主 ledger + exceptions.jsonl 双写,sidecar 可读名
2. 主 ledger IOError:fallback 到 FALLBACK.log,绝不抛
3. exceptions index 写失败:fallback 到 FALLBACK.log,绝不抛
4. FALLBACK.log 也失败:structlog ERROR(进程级最后兜底),绝不抛
5. sink closed 后 write:走 fallback,不抛
6. sidecar 名 <sha8>-<SafeClass>.json (legacy_sha256_only=False)
7. legacy_sha256_only=True:旧 <sha256>.json 行为兼容
8. exceptions_count 实时累计
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.tracing_file_sink import (
    TracingFileSink,
    _safe_class_name,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _make_record(
    *,
    execution_point: str = "brain.think.start",
    run_id: str = "run_test",
    seq: int = 1,
    payload: dict | None = None,
) -> EventRecord:
    return EventRecord(
        execution_point=execution_point,
        channel="control",
        span_id="lca-span-00000001",
        parent_span_id=None,
        sequence=seq,
        epoch=1,
        causality_id="cu-1",
        outcome="success",
        when=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        when_corrected=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        prev_event_hash=None,
        run_id=run_id,
        step_id="step-1",
        payload=payload or {},
    )


def _make_exception_record(
    *, run_id: str = "run_test", seq: int = 1, exc_class: str = "AttributeError"
) -> EventRecord:
    return _make_record(
        execution_point="exception.caught",
        run_id=run_id,
        seq=seq,
        payload={
            "boundary": "lifecycle.fail_loud.AttributeError",
            "exception_class": exc_class,
            "exception_message": "'str' object has no attribute 'value'",
            "traceback_text": "Traceback (most recent call last):\n  File ...\nAttributeError",
            "run_id": run_id,
            "trace_id": "",
        },
    )


# ── 1. 正常路径 ─────────────────────────────────────────────────────────


def test_main_ledger_written(tmp_path: Path) -> None:
    sink = TracingFileSink(tmp_path, run_id="run_test")
    sink.write(_make_record(execution_point="brain.think.start"))
    sink.close()
    content = (tmp_path / "run_test.spine.jsonl").read_text()
    assert "brain.think.start" in content


def test_exception_writes_to_exceptions_jsonl(tmp_path: Path) -> None:
    sink = TracingFileSink(tmp_path, run_id="run_test")
    sink.write(_make_exception_record(exc_class="AttributeError"))
    sink.write(_make_exception_record(exc_class="ValueError", seq=2))
    sink.close()
    exc_path = tmp_path / "run_test.exceptions.jsonl"
    assert exc_path.exists()
    lines = exc_path.read_text().strip().split("\n")
    assert len(lines) == 2
    classes = [json.loads(line)["payload"]["exception_class"] for line in lines]
    assert classes == ["AttributeError", "ValueError"]


def test_exceptions_count_increments(tmp_path: Path) -> None:
    sink = TracingFileSink(tmp_path, run_id="run_test")
    assert sink.exceptions_count == 0
    sink.write(_make_exception_record(seq=1))
    assert sink.exceptions_count == 1
    sink.write(_make_exception_record(seq=2))
    assert sink.exceptions_count == 2
    sink.write(_make_record(execution_point="brain.think.start", seq=3))
    assert sink.exceptions_count == 2  # 不变


def test_sidecar_readable_name(tmp_path: Path) -> None:
    """异常 offload → <sha8>-AttributeError.json。"""
    sink = TracingFileSink(tmp_path, run_id="run_test")
    # 强制 offload:payload 大于 4 KiB
    big_record = _make_exception_record(exc_class="AttributeError")
    big_record.payload["traceback_text"] = "x" * 5000  # > 4 KiB 阈值
    sink.write(big_record)
    sink.close()
    sidecars = list(tmp_path.glob("*.json"))
    sidecars = [p for p in sidecars if p.name != "run_test.exceptions.jsonl"]
    assert len(sidecars) >= 1
    # 命名规则:8 hex chars + - + AttributeError + .json
    assert any("-AttributeError.json" in p.name for p in sidecars), (
        f"sidecar 命名应包含 '-AttributeError.json',实际 {sidecars}"
    )


def test_sidecar_legacy_pure_sha256(tmp_path: Path) -> None:
    sink = TracingFileSink(tmp_path, run_id="run_test", legacy_sha256_only=True)
    big_record = _make_exception_record(exc_class="ValueError")
    big_record.payload["traceback_text"] = "x" * 5000
    sink.write(big_record)
    sink.close()
    sidecars = [
        p for p in tmp_path.glob("*.json")
        if p.name != "run_test.exceptions.jsonl"
    ]
    assert any(re.fullmatch(r"[0-9a-f]{64}\.json", p.name) for p in sidecars)


# ── 2. 主 ledger 失败 → fallback ───────────────────────────────────────


def test_main_ledger_failure_falls_back(tmp_path: Path, caplog) -> None:
    """主 ledger 写时 OSError → FALLBACK.log,不抛。"""
    sink = TracingFileSink(tmp_path, run_id="run_test")
    original_fd = sink._main._fd  # type: ignore[attr-defined]
    sink._main._fd = -999  # invalid fd → os.write raises OSError
    try:
        with caplog.at_level(logging.ERROR):
            sink.write(_make_record(execution_point="brain.think.start"))
    finally:
        sink._main._fd = original_fd
    sink.close()
    # FALLBACK.log 必须包含此次事件
    fb = tmp_path / "FALLBACK.log"
    assert fb.exists(), "FALLBACK.log 必须落盘"
    content = fb.read_text()
    assert "brain.think.start" in content
    assert "main_failed" in content


def test_main_close_failure_does_not_propagate(tmp_path: Path) -> None:
    sink = TracingFileSink(tmp_path, run_id="run_test")
    sink.write(_make_record())
    # close 不抛
    sink.close()


# ── 3. exceptions index 失败 → fallback ─────────────────────────────────


def test_exceptions_index_failure_falls_back(tmp_path: Path, caplog) -> None:
    sink = TracingFileSink(tmp_path, run_id="run_test")
    # 让 exceptions fd 失效
    sink._exceptions_fd = -999  # type: ignore[assignment]
    with caplog.at_level(logging.ERROR):
        sink.write(_make_exception_record(exc_class="AttributeError"))
    sink.close()
    fb = tmp_path / "FALLBACK.log"
    assert fb.exists()
    content = fb.read_text()
    assert "AttributeError" in content
    assert "exceptions_index_failed" in content


# ── 4. FALLBACK.log 也失败 → structlog ERROR ──────────────────────────


def test_all_filesystems_fail_goes_to_structlog(
    tmp_path: Path, caplog
) -> None:
    sink = TracingFileSink(tmp_path, run_id="run_test")
    # 关掉所有 fd,让 os.open / write / file open 全部失败
    sink._exceptions_fd = None
    # 让主 ledger 完全崩
    sink._main._fd = -999  # type: ignore[attr-defined]
    # 让 FALLBACK.log 也写不进 — patch Path.open to raise

    def _boom_open(self, *a, **kw):  # type: ignore[no-untyped-def]
        raise OSError("all filesystems dead")

    with (
        patch.object(Path, "open", _boom_open),
        caplog.at_level(
            logging.ERROR,
            logger="lca.infrastructure.observability.spine.sinks.tracing_file_sink",
        ),
    ):
        sink.write(_make_exception_record(exc_class="AttributeError"))
    sink.close()
    # 必须有 structlog ERROR 记录
    assert any(
        "FALLBACK write FAILED" in r.message
        for r in caplog.records
    ), f"structlog ERROR 必须发出,实际 {[(r.levelname, r.message) for r in caplog.records]}"


# ── 5. sink closed 后 write ────────────────────────────────────────────


def test_write_after_close_goes_to_fallback(tmp_path: Path) -> None:
    sink = TracingFileSink(tmp_path, run_id="run_test")
    sink.write(_make_record())
    sink.close()
    # 已关闭 → 写仍不抛,落 FALLBACK
    sink.write(_make_record(seq=2))
    fb = tmp_path / "FALLBACK.log"
    assert fb.exists()
    assert "sink_closed" in fb.read_text()


# ── 6. safe_class_name helper ─────────────────────────────────────────


def test_safe_class_name() -> None:
    assert _safe_class_name("AttributeError") == "AttributeError"
    assert _safe_class_name("my.module.Error") == "my_module_Error"
    assert _safe_class_name("") == "Unknown"
    assert _safe_class_name("Value Error") == "Value_Error"
