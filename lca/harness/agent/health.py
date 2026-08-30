"""Pure health projections over the live Session Spine activation cache."""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.harness.collaboration.agent import LiveAgentStatus

_STATUS_BUCKETS = {
    LiveAgentStatus.WORKING: "running",
    LiveAgentStatus.WAITING_INPUT: "waiting_input",
}


def status_counts(statuses: Iterable[LiveAgentStatus]) -> dict[str, int]:
    """Project live-agent statuses into the legacy health endpoint shape."""

    counts = {"pending": 0, "running": 0, "waiting_input": 0}
    for status in statuses:
        bucket = _STATUS_BUCKETS.get(status)
        if bucket is not None:
            counts[bucket] += 1
    return counts


def live_totals() -> dict[str, int]:
    """Return Session Spine's explicitly unsupported legacy live-tail metrics."""

    return {
        "total_subscribers": 0,
        "total_evicted": 0,
        "journal_subscribers": 0,
    }


__all__ = ["live_totals", "status_counts"]
