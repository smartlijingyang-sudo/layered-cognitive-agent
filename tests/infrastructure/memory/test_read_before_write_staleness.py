"""INV-READ-BEFORE-WRITE-STALENESS — a memory edit must target the latest disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.memory.contextfiles.domain.edit import (
    FileVersion,
    StaleSnapshotOperationError,
    require_fresh,
)


def test_matching_versions_pass() -> None:
    require_fresh(
        FileVersion(path="MEMORY.md", mtime_ns=100),
        FileVersion(path="MEMORY.md", mtime_ns=100),
    )


def test_mtime_change_raises() -> None:
    with pytest.raises(StaleSnapshotOperationError, match="changed during edit"):
        require_fresh(
            FileVersion(path="MEMORY.md", mtime_ns=100),
            FileVersion(path="MEMORY.md", mtime_ns=200),
        )


def test_path_change_raises() -> None:
    with pytest.raises(StaleSnapshotOperationError, match="changed during edit"):
        require_fresh(
            FileVersion(path="MEMORY.md", mtime_ns=100),
            FileVersion(path="USER.md", mtime_ns=100),
        )


def test_file_appearing_raises() -> None:
    with pytest.raises(StaleSnapshotOperationError, match="appeared during edit"):
        require_fresh(None, FileVersion(path="MEMORY.md", mtime_ns=100))


def test_file_disappearing_raises() -> None:
    with pytest.raises(StaleSnapshotOperationError, match="disappeared during edit"):
        require_fresh(FileVersion(path="MEMORY.md", mtime_ns=100), None)


def test_both_missing_pass() -> None:
    require_fresh(None, None)


def test_upsert_refuses_a_changed_semantic_store(tmp_path: Path) -> None:
    from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
    from lca.contracts.models.core.conversation.memory import MemoryRecord
    from lca.infrastructure.memory.assistant_memory import AssistantMemory

    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(
        MemoryRecord(
            record_id="city-1",
            content="用户住在杭州",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="city",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    original = memory._read_layer_text(MemoryLayer.SEMANTIC)

    def _stale_load(layer: MemoryLayer) -> tuple[str, list]:
        path = memory._layer_path(layer)
        path.write_text(original.replace("杭州", "上海"), encoding="utf-8")
        return original, __import__("json").loads(original)

    memory._load_with_text = _stale_load  # type: ignore[method-assign]
    with pytest.raises(StaleSnapshotOperationError):
        memory.upsert(
            MemoryRecord(
                record_id="city-2",
                content="用户住在北京",
                memory_type=MemoryLayer.SEMANTIC,
                importance=0.9,
                category=MemoryCategory.FACT,
                dedupe_key="city-2",
                confidence=1.0,
                metadata={"source": "user"},
            )
        )
    assert "北京" not in memory._read_layer_text(MemoryLayer.SEMANTIC)
