"""L2-7b: running-op endpoint returns a populated row when store is bound.

The endpoint's liveness gate (http.py) answers null unless the registry holds
a live session for the run, so the test binds a non-terminal RunSession.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from starlette.testclient import TestClient

from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.infrastructure.observability.running_operation_store import (
    SqliteRunningOperationStore,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunRegistry,
    RunSession,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.wire.http import (
    build_http_app,
)


def _bind_live_session(app: object, run_id: str, tmp_path: Path) -> None:
    """Put a non-terminal session into app.state.registry to satisfy the liveness gate."""
    registry = RunRegistry()
    registry.put(
        RunSession(
            run_id=run_id,
            trace_id="trace_test",
            spine_path=tmp_path / "run.spine.jsonl",
            tail=LiveTail(),
            question="hi",
            user_text="hi",
            mode="solo",
        )
    )
    app.state.registry = registry  # type: ignore[attr-defined]


def test_get_running_op_returns_row_when_present(tmp_path: Path) -> None:
    app = build_http_app()
    store = SqliteRunningOperationStore(":memory:")
    app.state.running_operation_store = store
    topic_id = f"topic_{uuid.uuid4().hex[:8]}"
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    _bind_live_session(app, run_id, tmp_path)
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
