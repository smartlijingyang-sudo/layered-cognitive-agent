"""WriteBehindBuffer + JsonlFileSink 单元测试。

覆盖：批量写入、定时触发、失败保留、背压丢弃、显式 flush、
dispose 排空、线程安全、文件追加正确性。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from lca.infrastructure.persistence.jsonl_sink import JsonlFileSink
from lca.infrastructure.persistence.write_behind import (
    DropPolicy,
    WriteBehindBuffer,
    WriteBehindSink,
)

# ── helpers ────────────────────────────────────────────────────────


class RecordingSink(WriteBehindSink):
    """测试用 sink：记录所有 append_batch 调用。"""

    def __init__(self, *, fail_on: set[int] | None = None) -> None:
        self.batches: list[list[Any]] = []
        self.closed = False
        self._call_count = 0
        self._fail_on = fail_on or set()

    def append_batch(self, events: list[Any]) -> None:
        self._call_count += 1
        if self._call_count in self._fail_on:
            raise OSError("simulated write failure")
        self.batches.append(list(events))

    def close(self) -> None:
        self.closed = True

    @property
    def all_events(self) -> list[Any]:
        return [e for batch in self.batches for e in batch]


class FailingSink(WriteBehindSink):
    """始终失败的 sink。"""

    def __init__(self) -> None:
        self.call_count = 0
        self.closed = False

    def append_batch(self, events: list[Any]) -> None:
        self.call_count += 1
        raise OSError("always fails")

    def close(self) -> None:
        self.closed = True


# ── WriteBehindBuffer ──────────────────────────────────────────────


class TestWriteBehindBufferBasic:
    def test_enqueue_and_flush(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        buf.enqueue({"id": 1})
        buf.enqueue({"id": 2})
        buf.flush()
        assert sink.all_events == [{"id": 1}, {"id": 2}]
        assert buf.pending_count == 0

    def test_flush_empty_buffer_is_noop(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        buf.flush()
        assert sink.batches == []

    def test_enqueue_copies_event(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        original = {"id": 1, "mutable": [1, 2]}
        buf.enqueue(original)
        original["mutable"].append(3)  # 修改原对象
        buf.flush()
        # buffer 中的拷贝不受影响
        assert sink.all_events[0]["mutable"] == [1, 2]

    def test_enqueue_without_copy(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        event = {"id": 1}
        buf.enqueue(event, copy_event=False)
        buf.flush()
        assert sink.all_events[0] is event

    def test_enqueue_after_close_raises(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        buf.dispose()
        with pytest.raises(RuntimeError, match="closed"):
            buf.enqueue({"id": 1})

    def test_invalid_params(self) -> None:
        sink = RecordingSink()
        with pytest.raises(ValueError, match="max_delay_ms"):
            WriteBehindBuffer(sink, max_delay_ms=0)
        with pytest.raises(ValueError, match="max_buffer_size"):
            WriteBehindBuffer(sink, max_buffer_size=-1)


class TestWriteBehindBufferTimer:
    def test_timer_fires_and_writes(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=50)
        buf.enqueue({"id": 1})
        # 等待定时器触发
        time.sleep(0.15)
        assert sink.all_events == [{"id": 1}]
        assert buf.pending_count == 0

    def test_multiple_events_in_one_batch(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=50)
        buf.enqueue({"id": 1})
        buf.enqueue({"id": 2})
        buf.enqueue({"id": 3})
        time.sleep(0.15)
        # 三条事件应在同一批
        assert len(sink.batches) == 1
        assert sink.all_events == [{"id": 1}, {"id": 2}, {"id": 3}]


class TestWriteBehindBufferFailure:
    def test_failure_retains_events(self) -> None:
        sink = FailingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        buf.enqueue({"id": 1})
        buf.enqueue({"id": 2})
        with pytest.raises(OSError):
            buf.flush()
        # 事件保留在 pending
        assert buf.pending_count == 2
        assert buf.failure_count == 1

    def test_failure_callback_invoked(self) -> None:
        sink = FailingSink()
        failures: list[Exception] = []
        buf = WriteBehindBuffer(
            sink,
            max_delay_ms=5000,
            on_failure=lambda e: failures.append(e),
        )
        buf.enqueue({"id": 1})
        with pytest.raises(OSError):
            buf.flush()
        assert len(failures) == 1
        assert "always fails" in str(failures[0])

    def test_failure_via_timer_retains_events(self) -> None:
        sink = FailingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=50)
        buf.enqueue({"id": 1})
        time.sleep(0.15)
        # 定时器触发的写入失败,事件保留
        assert buf.pending_count == 1
        assert buf.failure_count == 1

    def test_retry_after_failure(self) -> None:
        """第一次失败,第二次成功。"""
        sink = RecordingSink(fail_on={1})
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        buf.enqueue({"id": 1})
        with pytest.raises(OSError):
            buf.flush()
        assert buf.pending_count == 1
        # 再次 flush 应成功
        buf.flush()
        assert sink.all_events == [{"id": 1}]
        assert buf.pending_count == 0


class TestWriteBehindBufferBackpressure:
    def test_oldest_first_drop(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(
            sink,
            max_delay_ms=5000,
            max_buffer_size=3,
            drop_policy=DropPolicy.OLDEST_FIRST,
        )
        for i in range(5):
            buf.enqueue({"id": i})
        buf.flush()
        # 最旧的两条被丢弃,保留最新的三条
        assert sink.all_events == [{"id": 2}, {"id": 3}, {"id": 4}]
        assert buf.dropped_count == 2

    def test_newest_drop(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(
            sink,
            max_delay_ms=5000,
            max_buffer_size=3,
            drop_policy=DropPolicy.NEWEST,
        )
        for i in range(5):
            buf.enqueue({"id": i})
        buf.flush()
        # 前 3 条入队,后 2 条被丢弃
        assert sink.all_events == [{"id": 0}, {"id": 1}, {"id": 2}]
        assert buf.dropped_count == 2

    def test_never_drop_grows_unbounded(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(
            sink,
            max_delay_ms=5000,
            max_buffer_size=3,
            drop_policy=DropPolicy.NEVER,
        )
        for i in range(10):
            buf.enqueue({"id": i})
        assert buf.pending_count == 10
        buf.flush()
        assert len(sink.all_events) == 10


class TestWriteBehindBufferDispose:
    def test_dispose_flushes_and_closes(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        buf.enqueue({"id": 1})
        buf.enqueue({"id": 2})
        buf.dispose()
        assert sink.all_events == [{"id": 1}, {"id": 2}]
        assert sink.closed
        assert buf.is_closed

    def test_dispose_is_idempotent(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        buf.dispose()
        buf.dispose()
        assert sink.closed

    def test_dispose_with_empty_buffer(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        buf.dispose()
        assert sink.closed
        assert sink.batches == []


class TestWriteBehindBufferThreadSafety:
    def test_concurrent_enqueue(self) -> None:
        sink = RecordingSink()
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)
        errors: list[Exception] = []

        def worker(start: int) -> None:
            try:
                for i in range(start, start + 50):
                    buf.enqueue({"id": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        buf.flush()
        assert len(sink.all_events) == 200


# ── JsonlFileSink ──────────────────────────────────────────────────


class TestJsonlFileSink:
    def test_append_batch_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        sink = JsonlFileSink(path, fsync=False)
        sink.append_batch([{"id": 1}, {"id": 2}])
        sink.close()

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"id": 1}
        assert json.loads(lines[1]) == {"id": 2}

    def test_append_batch_appends_not_overwrites(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        sink = JsonlFileSink(path, fsync=False)
        sink.append_batch([{"id": 1}])
        sink.append_batch([{"id": 2}])
        sink.close()

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        sink = JsonlFileSink(path, fsync=False)
        sink.close()
        sink.close()

    def test_append_after_close_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        sink = JsonlFileSink(path, fsync=False)
        sink.close()
        with pytest.raises(RuntimeError, match="closed"):
            sink.append_batch([{"id": 1}])

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "test.jsonl"
        sink = JsonlFileSink(path, fsync=False)
        sink.append_batch([{"id": 1}])
        sink.close()
        assert path.exists()

    def test_custom_serializer(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        sink = JsonlFileSink(
            path,
            fsync=False,
            serializer=lambda e: {"custom": e["raw"]},
        )
        sink.append_batch([{"raw": "hello"}])
        sink.close()
        data = json.loads(path.read_text().strip())
        assert data == {"custom": "hello"}

    def test_empty_batch_is_noop(self, tmp_path: Path) -> None:
        path = tmp_path / "test.jsonl"
        sink = JsonlFileSink(path, fsync=False)
        sink.append_batch([])
        sink.close()
        assert not path.exists()


# ── Integration: WriteBehindBuffer + JsonlFileSink ─────────────────


class TestIntegration:
    def test_buffer_to_file(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        sink = JsonlFileSink(path, fsync=False)
        buf = WriteBehindBuffer(sink, max_delay_ms=50)

        buf.enqueue({"seq": 1, "type": "ToolStarted"})
        buf.enqueue({"seq": 2, "type": "ToolInvoked"})
        buf.dispose()

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["seq"] == 1
        assert json.loads(lines[1])["seq"] == 2

    def test_flush_then_more_events(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        sink = JsonlFileSink(path, fsync=False)
        buf = WriteBehindBuffer(sink, max_delay_ms=5000)

        buf.enqueue({"seq": 1})
        buf.flush()
        buf.enqueue({"seq": 2})
        buf.flush()
        buf.dispose()

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
