"""LcaStreamEventManager unit tests against a real Redis at 127.0.0.1:6379.

This is L1 (unit) but uses real Redis because mocking Redis semantics
falsifies the stream API. The dev Redis is part of the LCA dev stack
(``lca-ops infra start``).
"""
import asyncio
import json

import pytest

from lca.contracts.transport.stream_keys import stream_key
from lca.infrastructure.observability.stream.stream_event_manager import LcaStreamEventManager


@pytest.fixture
async def manager():
    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    mgr = LcaStreamEventManager(client)
    yield mgr
    await client.aclose()


async def test_publish_xadd_with_type_stepindex_data(manager):
    run_id = "test_publish_xadd"
    await manager.cleanup(run_id)
    event_id = await manager.publish(run_id, "stream_chunk", {"chunkType": "text", "content": "hi"}, step_index=0)
    assert "-" in event_id  # Redis-generated <ms>-<seq>
    await manager.cleanup(run_id)


async def test_publish_sets_ttl_7200(manager):
    run_id = "test_publish_ttl"
    await manager.cleanup(run_id)
    await manager.publish(run_id, "stream_chunk", {"chunkType": "text", "content": "x"}, step_index=0)
    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    ttl = await client.ttl(stream_key(run_id))
    await client.aclose()
    assert 7100 <= ttl <= 7200  # spec §5.1: TTL = 2 h
    await manager.cleanup(run_id)


async def test_publish_maxlen_caps_at_1000(manager):
    run_id = "test_maxlen"
    await manager.cleanup(run_id)
    for i in range(1500):
        await manager.publish(run_id, "stream_chunk", {"i": i}, step_index=i)
    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    length = await client.xlen(stream_key(run_id))
    await client.aclose()
    # approximate trim ~ 1000 (Redis may keep up to ~1100 due to ~)
    assert length <= 1200
    await manager.cleanup(run_id)


async def test_read_history_returns_events_in_descending_order(manager):
    run_id = "test_read_history"
    await manager.cleanup(run_id)
    for i in range(5):
        await manager.publish(run_id, "stream_chunk", {"i": i}, step_index=i)
    history = await manager.read_history(run_id, count=5)
    assert len(history) == 5
    # read_history returns newest first (XRANGE reverse); index 0 should be the last publish
    assert history[0]["data"]["i"] == 4
    assert history[-1]["data"]["i"] == 0
    await manager.cleanup(run_id)


async def test_exists_returns_true_when_key_alive(manager):
    run_id = "test_exists"
    await manager.cleanup(run_id)
    assert await manager.exists(run_id) is False
    await manager.publish(run_id, "stream_chunk", {}, step_index=0)
    assert await manager.exists(run_id) is True
    await manager.cleanup(run_id)
    assert await manager.exists(run_id) is False


async def test_subscribe_yields_only_events_after_last_id(manager):
    run_id = "test_subscribe_after"
    await manager.cleanup(run_id)
    e0 = await manager.publish(run_id, "stream_chunk", {"i": 0}, step_index=0)
    e1 = await manager.publish(run_id, "stream_chunk", {"i": 1}, step_index=1)
    e2 = await manager.publish(run_id, "stream_chunk", {"i": 2}, step_index=2)

    # Redis XREAD returns messages STRICTLY after the given id. Subscribing from
    # e0 yields e1 and e2; subscribing from e1 yields only e2. We assert the
    # former — the more useful contract.
    collected = []
    async def run():
        async for frame in manager.subscribe(run_id, e0):
            collected.append(frame)
            if len(collected) >= 2:
                return
    await asyncio.wait_for(run(), timeout=3.0)

    # Each frame is bytes of "id: <id>\nevent: agent_event\ndata: <json>\n\n"
    assert len(collected) == 2
    assert e1.encode() in collected[0]
    assert e2.encode() in collected[1]
    # e0 must NOT appear (Redis XREAD is strict-greater)
    assert e0.encode() not in collected[0]
    assert e0.encode() not in collected[1]
    await manager.cleanup(run_id)


async def test_data_field_is_json_stringified(manager):
    """spec §5.1: 'data is JSON-stringified' (Redis field)."""
    run_id = "test_data_json"
    await manager.cleanup(run_id)
    payload = {"chunkType": "text", "content": "x"}
    eid = await manager.publish(run_id, "stream_chunk", payload, step_index=0)

    import redis.asyncio as aioredis
    client = aioredis.from_url("redis://127.0.0.1:6379/0", decode_responses=True)
    fields = await client.xrange(stream_key(run_id), eid, eid)
    await client.aclose()
    assert len(fields) == 1
    # fields is a list of [id, {field: value, ...}]
    raw = fields[0][1]["data"]
    assert json.loads(raw) == payload
    await manager.cleanup(run_id)
