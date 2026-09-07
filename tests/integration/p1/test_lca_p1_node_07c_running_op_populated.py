"""L2-7b: running-op endpoint returns a populated row when store is bound."""

from __future__ import annotations

import uuid

from starlette.testclient import TestClient

from lca.infrastructure.observability.running_operation_store import (
    SqliteRunningOperationStore,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    build_http_app,
)


def test_get_running_op_returns_row_when_present() -> None:
    import asyncio

    app = build_http_app()
    store = SqliteRunningOperationStore(":memory:")
    app.state.running_operation_store = store
    topic_id = f"topic_{uuid.uuid4().hex[:8]}"
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    asyncio.run(
        store.insert(
            run_id=run_id,
            topic_id=topic_id,
            agent_id="solo",
            assistant_message_id="msg_1",
            scope="main",
        )
    )
    with TestClient(app) as client:
        resp = client.get(f"/v1/topics/{topic_id}/running-op")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running_operation"] is not None
    assert body["running_operation"]["run_id"] == run_id
    assert body["running_operation"]["topic_id"] == topic_id
