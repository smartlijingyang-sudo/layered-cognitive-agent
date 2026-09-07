"""RunningOperationStore Postgres contract tests (skip without dev Postgres)."""

from __future__ import annotations

import uuid

import pytest

from lca.infrastructure.persistence.postgres import postgres_available

pytestmark = pytest.mark.skipif(
    not postgres_available(),
    reason="requires Postgres at DATABASE_URL (lca-ops infra start)",
)


@pytest.fixture
async def store():
    from lca.infrastructure.observability.running_operation_store import (
        PostgresRunningOperationStore,
    )

    s = PostgresRunningOperationStore()
    yield s
    await s.delete_all_for_test()


@pytest.mark.asyncio
async def test_insert_then_get_latest_for_topic(store) -> None:
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
    assert row["accepted_answer_keys"] == []


@pytest.mark.asyncio
async def test_record_answer_key_appends(store) -> None:
    run_id = f"r_{uuid.uuid4().hex[:8]}"
    topic_id = f"t_{uuid.uuid4().hex[:8]}"
    await store.insert(run_id=run_id, topic_id=topic_id, agent_id="a1", assistant_message_id="m1", scope="main")
    await store.record_answer_key(run_id, "key1")
    await store.record_answer_key(run_id, "key1")
    row = await store.get_latest_for_topic(topic_id)
    assert row is not None
    assert row["accepted_answer_keys"] == ["key1"]
