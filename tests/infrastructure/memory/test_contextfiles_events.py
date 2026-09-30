"""Tests for the context-files event publisher and disk adapter.

The context-files architecture is observable through domain events and its
``FileStore`` port has a default filesystem adapter. These tests lock the
event vocabulary and the disk adapter's safety semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.events.publisher import (
    InProcessEventPublisher,
    ProjectionFailed,
    ProjectionWritten,
)


def _record(*, record_id: str, content: str) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.5,
        category=MemoryCategory.FACT,
        dedupe_key=record_id,
        source_trace_id="trace-1",
        created_at_ms=1_750_000_000_000,
        metadata={"source": "user", "trigger": "用户要求记下"},
    )


def test_disk_file_store_roundtrip_snapshot_and_list(tmp_path: Path) -> None:
    store = DiskFileStore(tmp_path)
    store.write_text("MEMORY.md", "# 长期记忆\n")
    assert store.read_text("MEMORY.md") == "# 长期记忆\n"
    assert store.exists("MEMORY.md")
    snapshot = store.snapshot("MEMORY.md")
    assert snapshot is not None
    assert snapshot.size_bytes == len("# 长期记忆\n".encode())
    assert snapshot.mtime_ns > 0
    assert store.list_dir("") == ("MEMORY.md",)


def test_disk_file_store_atomic_replace_leaves_no_temp_file(tmp_path: Path) -> None:
    store = DiskFileStore(tmp_path)
    store.atomic_replace("MEMORY.md", "v1")
    store.atomic_replace("MEMORY.md", "v2")
    assert store.read_text("MEMORY.md") == "v2"
    assert not (tmp_path / "MEMORY.md.tmp").exists()


def test_disk_file_store_rejects_path_escape(tmp_path: Path) -> None:
    store = DiskFileStore(tmp_path)
    with pytest.raises(ValueError):
        store.read_text("../outside")


def test_disk_file_store_missing_file_snapshot_is_none(tmp_path: Path) -> None:
    store = DiskFileStore(tmp_path)
    assert store.snapshot("nope.md") is None
    assert store.exists("nope.md") is False


def test_assistant_memory_publishes_projection_written_event(tmp_path: Path) -> None:
    publisher = InProcessEventPublisher()
    events: list[object] = []
    publisher.subscribe(events.append)
    memory = AssistantMemory(tmp_path / "asst", event_publisher=publisher)
    memory.upsert(_record(record_id="city-1", content="用户住在上海"))
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ProjectionWritten)
    assert event.path == str(tmp_path / "asst" / "MEMORY.md")
    assert event.byte_count > 0
    assert event.record_ids == ("city-1",)


def test_assistant_memory_publishes_projection_failed_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = InProcessEventPublisher()
    events: list[object] = []
    publisher.subscribe(events.append)
    memory = AssistantMemory(tmp_path / "asst", event_publisher=publisher)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("lca.infrastructure.memory.contextfiles.adapters.disk.os.replace", _boom)
    memory.upsert(_record(record_id="city-1", content="用户住在上海"))
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ProjectionFailed)
    assert "disk full" in event.error


def test_in_process_publisher_ignores_non_domain_events() -> None:
    publisher = InProcessEventPublisher()
    seen: list[object] = []
    publisher.subscribe(seen.append)
    publisher.publish(object())
    assert seen == []
