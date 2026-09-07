"""L2-6: Redis Stream key shape, TTL, MAXLEN.

Mirrors the L1 contract tests in
``lca/infrastructure/observability/stream/tests/test_stream_event_manager.py``;
this is the L2 contract — the same shape must hold from the gateway
side too.
"""

from __future__ import annotations

import asyncio
import uuid

import redis.asyncio as aioredis

from lca.contracts.transport.stream_keys import stream_key
from lca.infrastructure.observability.stream import LcaStreamEventManager


def test_key_prefix_is_agent_runtime_stream() -> None:
    assert stream_key("op1") == "agent_runtime_stream:op1"


def test_ttl_is_7200_seconds() -> None:
    async def _go() -> None:
        client = aioredis.from_url(
            "redis://127.0.0.1:6379/0", decode_responses=True
        )
        mgr = LcaStreamEventManager(client)
        run_id = f"l2_6_ttl_{uuid.uuid4().hex}"
        try:
            await mgr.publish(
                run_id, "stream_chunk", {"x": 1}, step_index=0
            )
            ttl = await client.ttl(stream_key(run_id))
            assert 7100 <= ttl <= 7200, f"unexpected TTL: {ttl}"
        finally:
            await mgr.cleanup(run_id)
            await client.aclose()

    asyncio.run(_go())


def test_maxlen_caps_around_1000() -> None:
    """Spec §5.1: MAXLEN ~ 1000 — write 1500, expect ≤ 1200 entries."""
    async def _go() -> None:
        client = aioredis.from_url(
            "redis://127.0.0.1:6379/0", decode_responses=True
        )
        mgr = LcaStreamEventManager(client)
        run_id = f"l2_6_maxlen_{uuid.uuid4().hex}"
        try:
            for i in range(1500):
                await mgr.publish(
                    run_id,
                    "stream_chunk",
                    {"i": i},
                    step_index=i + 1,
                )
            length = await client.xlen(stream_key(run_id))
            assert length <= 1200, f"stream grew past MAXLEN cap: {length}"
        finally:
            await mgr.cleanup(run_id)
            await client.aclose()

    asyncio.run(_go())