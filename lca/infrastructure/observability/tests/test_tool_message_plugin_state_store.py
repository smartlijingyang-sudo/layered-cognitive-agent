"""ToolMessagePluginStateStore unit tests."""

from __future__ import annotations

import pytest

from lca.infrastructure.observability.tool_message_plugin_state_store import (
    NoopToolMessagePluginStateStore,
    PostgresToolMessagePluginStateStore,
)


@pytest.mark.asyncio
async def test_noop_writer_accepts_write() -> None:
    store = NoopToolMessagePluginStateStore()
    await store.write(run_id="r1", tool_call_id="tc1", state={"stdout": "ok"})


def test_merge_hil_run_id_injects_lca_run_id() -> None:
    merged = PostgresToolMessagePluginStateStore._merge_hil_run_id(
        "run_abc",
        {"stdout": "ok"},
    )
    assert merged["stdout"] == "ok"
    assert merged["lca"]["run_id"] == "run_abc"


def test_merge_hil_run_id_preserves_existing_lca_fields() -> None:
    merged = PostgresToolMessagePluginStateStore._merge_hil_run_id(
        "run_new",
        {"lca": {"run_id": "run_old", "status": "waiting_input"}},
    )
    assert merged["lca"]["run_id"] == "run_old"
    assert merged["lca"]["status"] == "waiting_input"
