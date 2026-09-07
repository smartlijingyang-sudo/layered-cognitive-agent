"""PR-5 quick stability smoke for P1 gateway bridge wiring."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.stability


def test_coordinator_factory_wires_plugin_state_writer() -> None:
    """``build_agent_runtime_coordinator`` delegates tool_state_writer to plugin store."""
    import asyncio
    from unittest.mock import AsyncMock

    from lca.infrastructure.observability.running_operation_store import (
        SqliteRunningOperationStore,
    )
    from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.coordinator_factory import (
        build_agent_runtime_coordinator,
    )

    store = SqliteRunningOperationStore(":memory:")
    plugin_store = AsyncMock()
    coord = build_agent_runtime_coordinator(store, plugin_state_store=plugin_store)
    asyncio.run(
        coord._tool_state_writer(
            run_id="run_1",
            tool_call_id="tc1",
            state={"stdout": "ok"},
        )
    )
    plugin_store.write.assert_awaited_once_with(
        run_id="run_1",
        tool_call_id="tc1",
        state={"stdout": "ok"},
    )


def test_running_operation_store_resolver_returns_sqlite_without_pg() -> None:
    from lca.infrastructure.observability.running_operation_store import (
        SqliteRunningOperationStore,
        resolve_running_operation_store,
    )

    prev = os.environ.pop("DATABASE_URL", None)
    try:
        resolved = resolve_running_operation_store()
        assert isinstance(resolved, SqliteRunningOperationStore)
    finally:
        if prev is not None:
            os.environ["DATABASE_URL"] = prev


def test_one_hour_stability() -> None:
    """Full 1 h scenario — nightly only (``LCA_STABILITY=1``)."""
    if os.environ.get("LCA_STABILITY") != "1":
        pytest.skip("nightly only; set LCA_STABILITY=1 for the 1 h run")

    import asyncio

    from tests.e2e.p1._lca_gateway_client import LcaGatewayClient

    async def _run() -> dict:
        client = LcaGatewayClient(base_url=os.environ.get("LCA_GATEWAY_URL", "http://127.0.0.1:9876"))
        try:
            from tests.e2e.p1._stability_loop import run_stability

            return await run_stability(client)
        finally:
            await client.close()

    summary = asyncio.run(_run())
    assert summary.get("timed_out") is not True, "stability run did not complete in 55 min"
    assert summary.get("terminal_reason") == "completed", summary
