"""L2-2: ``resume`` replays history and emits ``resume_complete``.

The gateway reads ``lastEventId`` and emits every Redis stream entry
whose id > ``lastEventId``; when ``want_status=True`` it also emits
``resume_complete`` so the client knows when to stop replaying.
"""

from __future__ import annotations

import asyncio
import uuid

from starlette.testclient import TestClient

from lca.infrastructure.observability.stream import (
    LcaStreamEventManager,
    get_agent_runtime_redis_client,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.auth import (
    mint_user_jwt,
)


def _publish_initial_events(run_id: str) -> None:
    """Seed the run with two events so resume has something to replay."""

    async def _seed() -> None:
        mgr = LcaStreamEventManager(get_agent_runtime_redis_client())
        await mgr.publish(
            run_id,
            "agent_runtime_init",
            {"agentId": "a1"},
            step_index=0,
        )
        await mgr.publish(
            run_id,
            "stream_chunk",
            {"chunkType": "text", "content": "hello"},
            step_index=1,
        )

    asyncio.run(_seed())


def _cleanup(run_id: str) -> None:
    async def _go() -> None:
        mgr = LcaStreamEventManager(get_agent_runtime_redis_client())
        await mgr.cleanup(run_id)

    asyncio.run(_go())


def test_resume_replays_events_and_emits_resume_complete(
    lca_gateway_app, rsa_keys: dict[str, str]
) -> None:
    run_id = uuid.uuid4().hex
    try:
        _publish_initial_events(run_id)
        token = mint_user_jwt(
            user_id="u1",
            operation_id=run_id,
            private_key_pem=rsa_keys["private"],
            ttl_seconds=60,
        )
        with TestClient(lca_gateway_app) as client:
            with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
                ws.send_json({"type": "auth", "token": token})
                assert ws.receive_json() == {"type": "auth_success"}
                ws.send_json(
                    {"type": "resume", "lastEventId": "0", "wantStatus": True}
                )

                seen_init = False
                seen_chunk = False
                seen_complete = False
                # Read frames until we see resume_complete, or 20 frames.
                for _ in range(20):
                    try:
                        frame = ws.receive_json()
                    except Exception:
                        break
                    ftype = frame.get("type")
                    if ftype == "agent_event":
                        inner = frame.get("event", {})
                        inner_type = inner.get("type")
                        if inner_type == "agent_runtime_init":
                            seen_init = True
                        elif inner_type == "stream_chunk":
                            seen_chunk = True
                    elif ftype == "resume_complete":
                        seen_complete = True
                        # break — no live events yet, completion is the last frame
                        break

                assert seen_init, "expected agent_runtime_init replay"
                assert seen_chunk, "expected stream_chunk replay"
                assert seen_complete, "expected resume_complete"
    finally:
        _cleanup(run_id)


def test_resume_with_zero_events_emits_only_resume_complete(
    lca_gateway_app, rsa_keys: dict[str, str]
) -> None:
    """A run with no history still emits ``resume_complete``."""
    run_id = uuid.uuid4().hex
    try:
        token = mint_user_jwt(
            user_id="u1",
            operation_id=run_id,
            private_key_pem=rsa_keys["private"],
            ttl_seconds=60,
        )
        with TestClient(lca_gateway_app) as client:
            with client.websocket_connect(f"/v1/runs/{run_id}/ws") as ws:
                ws.send_json({"type": "auth", "token": token})
                assert ws.receive_json() == {"type": "auth_success"}
                ws.send_json(
                    {"type": "resume", "lastEventId": "0", "wantStatus": True}
                )
                seen_complete = False
                for _ in range(10):
                    try:
                        frame = ws.receive_json()
                    except Exception:
                        break
                    if frame.get("type") == "resume_complete":
                        seen_complete = True
                        break
                assert seen_complete
    finally:
        _cleanup(run_id)
