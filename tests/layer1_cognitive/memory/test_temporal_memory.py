from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.enums import ContentType, MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.memory import MemoryRecord, MemoryRelationKind, MemoryTrust
from lca.contracts.models.core.state import AgentState, Budget
from lca.infrastructure.state_store.sqlite_temporal_memory import SqliteTemporalMemoryStore
from lca.layer1_cognitive.memory.temporal_memory import TemporalMemorySystem


def _record(
    record_id: str, content: str, *, scope_id: str = "project:a", valid_from_ms: int = 100
) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        content=content,
        memory_type=MemoryLayer.SEMANTIC,
        importance=0.8,
        scope_id=scope_id,
        provenance="user_confirmed",
        valid_from_ms=valid_from_ms,
    )


def test_sqlite_store_revises_without_losing_historical_view(tmp_path: Path) -> None:
    store = SqliteTemporalMemoryStore(tmp_path / "memory.sqlite3")
    original = store.remember(_record("fact-v1", "User prefers dark mode"))
    revised = store.revise(
        original.record_id,
        _record("fact-v2", "User prefers light mode", valid_from_ms=200),
        reason="user changed preference",
    )

    historical = store.recall(scope_id="project:a", query="dark", as_of_ms=150)
    current = store.recall(scope_id="project:a", query="light", as_of_ms=250)

    assert [record.record_id for record in historical] == [original.record_id]
    assert [record.record_id for record in current] == [revised.record_id]
    assert revised.revision_of == original.record_id
    assert store.recall(scope_id="project:a", query="dark", as_of_ms=250) == []


def test_sqlite_store_enforces_scope_and_soft_retirement(tmp_path: Path) -> None:
    store = SqliteTemporalMemoryStore(tmp_path / "memory.sqlite3")
    visible = store.remember(
        _record("project-a", "Project A has a migration", scope_id="project:a")
    )
    store.remember(_record("project-b", "Project B has a credential", scope_id="project:b"))
    store.retire(visible.record_id, reason="obsolete", at_ms=200)

    assert (
        store.recall(scope_id="project:a", query="migration", as_of_ms=150)[0].record_id
        == visible.record_id
    )
    assert store.recall(scope_id="project:a", query="migration", as_of_ms=250) == []
    assert (
        store.recall(scope_id="project:b", query="credential", as_of_ms=250)[0].record_id
        == "project-b"
    )
    retired = store.list_records(scope_id="project:a", include_retired=True)
    assert retired[0].deleted is True
    assert retired[0].metadata["retirement_reason"] == "obsolete"


def test_sqlite_store_persists_explicit_relationships(tmp_path: Path) -> None:
    store = SqliteTemporalMemoryStore(tmp_path / "memory.sqlite3")
    first = store.remember(_record("first", "A proposal exists"))
    second = store.remember(_record("second", "A stronger proposal exists"))

    store.relate(first.record_id, second.record_id, MemoryRelationKind.EXTENDS)

    with store._lock:  # Verify the storage-level edge without widening the public read API.
        row = store._conn.execute(
            "SELECT relation FROM temporal_memory_relation WHERE source_id = ? AND target_id = ?",
            (first.record_id, second.record_id),
        ).fetchone()
    assert row is not None
    assert row["relation"] == MemoryRelationKind.EXTENDS.value


@pytest.mark.asyncio
async def test_temporal_memory_marks_recall_as_untrusted_and_archives_turn(tmp_path: Path) -> None:
    memory = TemporalMemorySystem(db_path=tmp_path / "memory.sqlite3", scope_id="project:a")
    memory.remember(content="The project uses SQLite", scope_id="project:a")
    state = AgentState(
        trace_id="trace-1", task="Does the project use SQLite?", budget=Budget(), step=3
    )

    perceived = await memory.perceive(state)
    observation = Observation(
        observation_id="obs-1",
        success=True,
        payload="yes",
        content_type=ContentType.TEXT,
    )
    reflection = Reflection(
        reflection_id="refl-1", verdict=ReflectionVerdict.ON_TRACK, lesson="keep tests"
    )
    await memory.update(state, observation, reflection)

    assert state.retrieved_context == []
    assert perceived.retrieved_context[0].trust is MemoryTrust.UNTRUSTED_HISTORY
    assert perceived.retrieved_context[0].metadata["recall_query"] == state.task
    episodic = memory.query(MemoryLayer.EPISODIC)
    assert len(episodic) == 1
    assert episodic[0].metadata["source"] == "automatic_turn_archive"
    assert "lesson=keep tests" in episodic[0].content
