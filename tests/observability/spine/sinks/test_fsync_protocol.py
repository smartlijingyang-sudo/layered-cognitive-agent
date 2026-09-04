"""FsyncProtocol 契约枚举与各 sink 的显式声明一致性(DSH-GAP G2 / note 2)。

覆盖:
- 契约枚举闭集存在于 ``lca.contracts.observability.fsync``
  (``ssot`` re-export 同一对象);
- kernel persistence 侧与契约层是同一枚举(无双枚举);
- FileSink 主账本 fd 默认 BATCH、exceptions 索引 fd 声明 COMMIT;
- 三种 protocol 的 fsync 触发行为(os.fsync 计数);
- TracingFileSink fallback 路径强制 PER_WRITE(每行 fsync)。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.observability.fsync import FsyncProtocol
from lca.contracts.observability.ssot import FsyncProtocol as SsotFsyncProtocol
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
from lca.infrastructure.observability.spine.sinks.tracing_file_sink import (
    TracingFileSink,
)
from lca_kernel.events.persistence import FsyncProtocol as KernelFsyncProtocol


def _make_rec(**overrides: Any) -> EventRecord:
    base = {
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
    return EventRecord(**base)


@pytest.fixture
def fsync_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Replace os.fsync with a counter; returns the mutable count list."""
    calls: list[int] = [0]

    def _counting_fsync(fd: int) -> None:
        calls[0] += 1

    monkeypatch.setattr(os, "fsync", _counting_fsync)
    return calls


class TestContractEnum:
    def test_members_are_closed_set(self) -> None:
        assert {m.value for m in FsyncProtocol} == {"per_write", "batch", "commit"}

    def test_ssot_reexport_is_same_enum(self) -> None:
        assert SsotFsyncProtocol is FsyncProtocol

    def test_kernel_persistence_uses_contract_enum(self) -> None:
        assert KernelFsyncProtocol is FsyncProtocol


class TestFileSinkProtocolDeclarations:
    def test_default_ledger_protocol_is_batch(self, tmp_path: Path) -> None:
        sink = FileSink(tmp_path, run_id="r1")
        assert sink.fsync_protocol is FsyncProtocol.BATCH
        sink.close()

    def test_ledger_protocol_constructor_override(self, tmp_path: Path) -> None:
        sink = FileSink(tmp_path, run_id="r1", fsync_protocol=FsyncProtocol.PER_WRITE)
        assert sink.fsync_protocol is FsyncProtocol.PER_WRITE
        sink.close()

    def test_exceptions_index_protocol_is_commit(self) -> None:
        assert FileSink.EXCEPTIONS_INDEX_PROTOCOL is FsyncProtocol.COMMIT


class TestFileSinkFsyncBehavior:
    def test_per_write_fsyncs_every_write_and_skips_close(
        self, tmp_path: Path, fsync_counter: list[int]
    ) -> None:
        sink = FileSink(
            tmp_path,
            run_id="r1",
            fsync_protocol=FsyncProtocol.PER_WRITE,
            write_exception_index=False,
        )
        for seq in (1, 2, 3):
            sink.write(_make_rec(sequence=seq))
        assert fsync_counter[0] == 3
        sink.close()
        # close 不重复 fsync 已逐条落盘的 fd。
        assert fsync_counter[0] == 3

    def test_batch_fsyncs_on_threshold_and_forces_close(
        self, tmp_path: Path, fsync_counter: list[int]
    ) -> None:
        sink = FileSink(
            tmp_path,
            run_id="r1",
            fsync_protocol=FsyncProtocol.BATCH,
            fsync_batch=2,
            fsync_interval_ms=3_600_000,
            write_exception_index=False,
        )
        for seq in (1, 2, 3):
            sink.write(_make_rec(sequence=seq))
        assert fsync_counter[0] == 1
        sink.close()
        assert fsync_counter[0] == 2

    def test_commit_skips_runtime_fsync_and_sync_on_close(
        self, tmp_path: Path, fsync_counter: list[int]
    ) -> None:
        sink = FileSink(
            tmp_path,
            run_id="r1",
            fsync_protocol=FsyncProtocol.COMMIT,
            write_exception_index=False,
        )
        for seq in (1, 2, 3):
            sink.write(_make_rec(sequence=seq))
        assert fsync_counter[0] == 0
        sink.close()
        assert fsync_counter[0] == 1

    def test_close_fsyncs_commit_exceptions_index(
        self, tmp_path: Path, fsync_counter: list[int]
    ) -> None:
        sink = FileSink(
            tmp_path,
            run_id="r1",
            fsync_protocol=FsyncProtocol.PER_WRITE,
            write_exception_index=True,
        )
        sink.write(_make_rec())
        assert fsync_counter[0] == 1  # 主账本 PER_WRITE,索引运行期不 fsync
        sink.close()
        # close:主账本 PER_WRITE 跳过,索引 COMMIT 补一次。
        assert fsync_counter[0] == 2


class TestTracingFileSinkFallback:
    def test_fallback_protocol_is_per_write(self) -> None:
        assert TracingFileSink.FALLBACK_FSYNC_PROTOCOL is FsyncProtocol.PER_WRITE

    def test_fsync_protocol_forwards_to_main_sink(self, tmp_path: Path) -> None:
        sink = TracingFileSink(tmp_path, run_id="r1", fsync_protocol=FsyncProtocol.PER_WRITE)
        assert sink.fsync_protocol is FsyncProtocol.PER_WRITE
        sink.close()

    def test_fallback_line_is_fsynced_per_write(
        self, tmp_path: Path, fsync_counter: list[int]
    ) -> None:
        sink = TracingFileSink(tmp_path, run_id="r1")
        sink.close()
        # close 的 ledger/索引 fsync 不计入兜底断言。
        fsync_counter[0] = 0
        # close 后 write 走 FALLBACK.log 兜底路径。
        sink.write(_make_rec())
        assert fsync_counter[0] == 1
        fallback = tmp_path / "FALLBACK.log"
        lines = fallback.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["fallback_reason"] == "sink_closed"
