"""GET /runs/{id}/live retired in P1 — route removed from carrier."""

from __future__ import annotations

from lca.plugins.transport.webserver.routes_2.routes_runs_sessions import ROUTE_SPECS


def test_live_route_is_not_registered() -> None:
    """P1 retires GET /runs/{id}/live in favour of the WS gateway."""
    paths = {spec.path for spec in ROUTE_SPECS}
    assert "/runs/{run_id}/live" not in paths
    assert "/v1/runs/{run_id}/ws-token" in paths
