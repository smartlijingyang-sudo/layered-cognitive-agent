"""Tests for pure Session Spine health projections."""

from __future__ import annotations

from lca.contracts.harness.agent import LiveAgentStatus
from lca.harness.agent.health import live_totals, status_counts


def test_status_counts_projects_only_exposed_live_buckets() -> None:
    """Internal idle/disposed states must not leak into legacy health payloads."""

    assert status_counts(
        [
            LiveAgentStatus.IDLE,
            LiveAgentStatus.WORKING,
            LiveAgentStatus.WAITING_INPUT,
            LiveAgentStatus.DISPOSED,
        ]
    ) == {"pending": 0, "running": 1, "waiting_input": 1}


def test_live_totals_explicitly_reports_unsupported_legacy_tail_metrics() -> None:
    """Session Spine has no legacy process-tail owner to fabricate metrics for."""

    assert live_totals() == {
        "total_subscribers": 0,
        "total_evicted": 0,
        "journal_subscribers": 0,
    }
