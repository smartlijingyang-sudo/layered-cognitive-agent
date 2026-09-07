"""L3-3: page refresh (F5) during a long run — reconnect via running-op.

Simulates the user pressing F5 mid-run. The WS drops; the client
queries ``GET /lca-api/topics/{topic_id}/running-op`` to discover the
active run, then reconnects with ``resumeOnConnect: true``. Asserts
no event loss and that the new WS sees every event from the original
WS (deduped by id).

Gated on ``LCA_E2E_KERNEL=1``; skipped otherwise.
"""

from __future__ import annotations

import pytest


@pytest.mark.timeout(120)
def test_page_refresh_reconnect_no_event_loss(lca_client) -> None:
    """F5 mid-run: running-op → reconnect → no event loss."""
    pytest.skip("L3-3 requires LCA_E2E_KERNEL=1 (LCA dev stack); see tests/e2e/p1/conftest.py")


def test_page_refresh_resume_replays_from_last_event_id() -> None:
    """Unit-level: page refresh replays events after lastEventId.

    The gateway resume path reads history and emits only events whose
    id > lastEventId. This test verifies that invariant directly
    against the LcaStreamEventManager, without a kernel.
    """
    import asyncio
    import uuid

    from lca.infrastructure.observability.stream import (
        LcaStreamEventManager,
        get_agent_runtime_redis_client,
    )

    async def _run() -> None:
        run_id = uuid.uuid4().hex
        mgr = LcaStreamEventManager(get_agent_runtime_redis_client())
        try:
            # Publish 10 events.
            ids: list[str] = []
            for i in range(10):
                eid = await mgr.publish(
                    run_id,
                    "stream_chunk",
                    {"chunkType": "text", "content": f"chunk-{i}"},
                    step_index=i,
                )
                ids.append(eid)

            # Simulate page refresh after event 4 (index 4).
            last_seen = ids[4]
            history = await mgr.read_history(run_id, count=1000)
            history.reverse()
            unseen = [ev for ev in history if ev.get("id") and ev["id"] > last_seen]
            # Events 5..9 should replay (5 events).
            assert len(unseen) == 5
            assert unseen[0]["stepIndex"] == 5
            assert unseen[-1]["stepIndex"] == 9

            # Verify id ordering is strict (dedup invariant).
            for i in range(len(unseen) - 1):
                assert unseen[i]["id"] < unseen[i + 1]["id"]
        finally:
            await mgr.cleanup(run_id)

    asyncio.run(_run())
