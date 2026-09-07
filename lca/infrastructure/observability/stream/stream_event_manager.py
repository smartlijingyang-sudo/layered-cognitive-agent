"""LcaStreamEventManager — Redis Stream backing the agent runtime event bus.

This is a 1:1 Python mirror of the TypeScript implementation in
`apps/server/src/modules/AgentRuntime/StreamEventManager.ts:139-211`. The
Redis layout is wire-compat: the same XADD fields (`type`, `stepIndex`,
`operationId`, `data`, `timestamp`), the same key prefix
(`agent_runtime_stream:`), the same TTL (2 h), the same MAXLEN (~1000).

It is consumed by:
- `LcaAgentRuntimeCoordinator` (publishes events on state transitions)
- `LcaAgentGateway` (subscribes for WebSocket clients)
- `useGatewayReconnect` liveness check (EXISTS)
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from lca.contracts.transport.stream_keys import (
    STREAM_MAXLEN,
    STREAM_RETENTION_SECONDS,
    stream_key,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis


class LcaStreamEventManager:
    """Redis Stream event bus, native-wire-compat."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    # ── Write side ────────────────────────────────────────────────────

    async def publish(
        self,
        run_id: str,
        type: str,
        data: dict,
        *,
        step_index: int,
    ) -> str:
        """XADD an event to the run's stream; refresh TTL.

        Returns the Redis-generated event id (`<ms>-<seq>`).
        """
        # Parse STREAM_MAXLEN: native uses `"~1000"` (approximate trim).
        # redis-py expects maxlen as int + approximate=True.
        maxlen_str = STREAM_MAXLEN.lstrip("~")
        maxlen_int = int(maxlen_str)
        approximate = STREAM_MAXLEN.startswith("~")

        event_id = await self._redis.xadd(
            stream_key(run_id),
            {
                "type": type,
                "stepIndex": str(step_index),
                "operationId": run_id,
                "data": json.dumps(data),
                "timestamp": str(_now_ms()),
            },
            id="*",
            maxlen=maxlen_int,
            approximate=approximate,
        )
        await self._redis.expire(stream_key(run_id), STREAM_RETENTION_SECONDS)
        # Redis-py returns bytes when decode_responses=False, str when True.
        # Normalise to str for the caller.
        return str(event_id)

    async def cleanup(self, run_id: str) -> None:
        """Delete the run's stream key. Called on `agent_runtime_end`."""
        await self._redis.delete(stream_key(run_id))

    async def exists(self, run_id: str) -> bool:
        """Liveness check used by useGatewayReconnect."""
        return bool(await self._redis.exists(stream_key(run_id)))

    async def last_id(self, run_id: str) -> str | None:
        """Return the most recent event id in the stream, or None if empty."""
        result = await self._redis.xrevrange(stream_key(run_id), "+", "-", count=1)
        if not result:
            return None
        return str(result[0][0])

    # ── Read side ─────────────────────────────────────────────────────

    async def read_history(self, run_id: str, count: int) -> list[dict]:
        """Return up to `count` most recent events, newest first."""
        result = await self._redis.xrevrange(stream_key(run_id), "+", "-", count=count)
        return [_parse_redis_stream_row(row) for row in result]

    async def subscribe(
        self,
        run_id: str,
        last_id: str,
        *,
        signal: object | None = None,  # asyncio.AbortSignal | None
    ) -> AsyncIterator[bytes]:
        """Block on XREAD and yield SSE-encoded `agent_event` frames.

        Each yielded frame is bytes shaped:
            b"id: <redis_id>\\nevent: agent_event\\ndata: <json>\\n\\n"

        The caller (LcaAgentGateway) writes these directly to the
        WebSocket. Aborts cleanly on `signal.aborted`.
        """
        key = stream_key(run_id)
        current_last_id = last_id
        while signal is None or not getattr(signal, "aborted", False):
            try:
                # redis-py 8.x signature: xread(streams={key: last_id}, block=ms, count=None)
                results = await self._redis.xread(
                    {key: current_last_id},
                    block=1000,
                )
            except Exception:
                # Transient: retry after 1 s. Native has the same loop.
                await asyncio.sleep(1.0)
                continue

            if not results:
                continue
            for _, messages in results:
                for msg_id, fields in messages:
                    current_last_id = str(msg_id)
                    event = _parse_redis_stream_row((str(msg_id), fields))
                    yield _encode_sse_agent_event(event)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_redis_stream_row(row: tuple[object, dict[str, object]]) -> dict[str, object]:
    msg_id, fields = row
    out: dict[str, object] = {"id": msg_id, "type": fields.get("type")}
    try:
        out["stepIndex"] = int(fields.get("stepIndex", "0"))
    except (TypeError, ValueError):
        out["stepIndex"] = 0
    out["operationId"] = fields.get("operationId")
    try:
        out["timestamp"] = int(fields.get("timestamp", "0"))
    except (TypeError, ValueError):
        out["timestamp"] = 0
    raw_data = fields.get("data")
    if raw_data:
        try:
            out["data"] = json.loads(raw_data)
        except json.JSONDecodeError:
            out["data"] = None
    return out


def _encode_sse_agent_event(event: dict) -> bytes:
    """SSE-encode a single agent event for WebSocket transport.

    The wire shape is `agent_event` (server → client); the WebSocket
    envelope wraps the JSON. See spec §7.
    """
    envelope = {
        "type": "agent_event",
        "id": event.get("id"),
        "event": {
            "type": event.get("type"),
            "data": event.get("data"),
            "operationId": event.get("operationId"),
            "stepIndex": event.get("stepIndex", 0),
            "timestamp": event.get("timestamp", 0),
        },
    }
    body = json.dumps(envelope, ensure_ascii=False)
    event_id = event.get("id") or ""
    return (
        f"id: {event_id}\nevent: agent_event\ndata: {body}\n\n"
    ).encode()


__all__ = ("LcaStreamEventManager",)
