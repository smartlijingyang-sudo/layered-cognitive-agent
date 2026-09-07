"""Short stability loop for nightly L4-1 (full scenario delegates to e2e client)."""

from __future__ import annotations

import time
from typing import Any

from tests.e2e.p1._lca_gateway_client import LcaGatewayClient


async def run_stability(client: LcaGatewayClient) -> dict[str, Any]:
    """Drive a long-running gateway session; returns summary for assertions."""
    start = time.time()
    receipt = await client.start_run(
        agent_id="a1",
        messages=[
            {
                "role": "user",
                "content": "stability test — long running task with many tool calls and HIL",
            }
        ],
    )
    run_id = receipt["run_id"]
    token = receipt["ws_token"]
    await client.connect_ws(run_id, token)
    await client.resume(last_event_id="0", want_status=True)

    all_events: list[dict] = []
    terminal_reason: str | None = None

    while time.time() - start < 3300:
        events = await client.collect_events(timeout=10.0, max_events=500)
        all_events.extend(events)
        for event in events:
            if event.get("type") == "agent_runtime_end":
                terminal_reason = event.get("data", {}).get("reason")
                if terminal_reason in ("completed", "error", "interrupted"):
                    return {
                        "run_id": run_id,
                        "events": all_events,
                        "terminal_reason": terminal_reason,
                        "duration_s": time.time() - start,
                    }

    return {
        "run_id": run_id,
        "events": all_events,
        "terminal_reason": terminal_reason,
        "duration_s": time.time() - start,
        "timed_out": True,
    }


__all__ = ("run_stability",)
