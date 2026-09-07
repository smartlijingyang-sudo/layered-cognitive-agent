"""RunningOperationStore contract tests (SQLite backend)."""

from __future__ import annotations

import uuid

import pytest

from lca.infrastructure.observability.running_operation_store import (
    SqliteRunningOperationStore,
)


@pytest.fixture
async def store() -> SqliteRunningOperationStore:
    s = SqliteRunningOperationStore(":memory:")
    yield s
    await s.delete_all_for_test()


@pytest.mark.asyncio
async def test_insert_then_get_latest_for_topic(store: SqliteRunningOperationStore) -> None:
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    await store.insert(
        run_id=run_id,
        topic_id=topic_id,
        agent_id="a1",
        assistant_message_id="m1",
        scope="main",
    )
    row = await store.get_latest_for_topic(topic_id)
    assert row is not None
    assert row["run_id"] == run_id
    assert row["topic_id"] == topic_id
    assert row["agent_id"] == "a1"
    assert row["assistant_message_id"] == "m1"
    assert row["scope"] == "main"
    assert row["accepted_answer_keys"] == []


@pytest.mark.asyncio
async def test_get_latest_for_topic_returns_none_for_missing(
    store: SqliteRunningOperationStore,
) -> None:
    row = await store.get_latest_for_topic(f"missing_{uuid.uuid4().hex[:8]}")
    assert row is None


@pytest.mark.asyncio
async def test_record_answer_key_appends_to_jsonb(store: SqliteRunningOperationStore) -> None:
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    await store.insert(run_id=run_id, topic_id=topic_id, agent_id="a1", assistant_message_id="m1", scope="main")
    await store.record_answer_key(run_id, "key1")
    await store.record_answer_key(run_id, "key1")
    row = await store.get_latest_for_topic(topic_id)
    assert row is not None
    assert row["accepted_answer_keys"] == ["key1"]


@pytest.mark.asyncio
async def test_delete_removes_row(store: SqliteRunningOperationStore) -> None:
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    await store.insert(run_id=run_id, topic_id=topic_id, agent_id="a1", assistant_message_id=None, scope="main")
    await store.delete(run_id)
    assert await store.get_latest_for_topic(topic_id) is None
