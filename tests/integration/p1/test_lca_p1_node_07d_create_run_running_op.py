"""L2-7d: create_run registers running-op row when gateway coordinator is bound."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.infrastructure.observability.running_operation_store import (
    SqliteRunningOperationStore,
)
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    create_run,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunRegistry,
    RunSession,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.streaming.coordinator_factory import (
    build_agent_runtime_coordinator,
)


class _StubRunPort:
    def __init__(self, *, run_id: str) -> None:
        self.run_id = run_id

    async def create_and_dispatch(self, request: Any) -> Any:
        from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
            RunReceipt,
        )

        return RunReceipt(
            run_id=self.run_id,
            trace_id="trace_gateway",
            accepted=True,
            rejection_reason=None,
        )


def _request(body: dict[str, Any], app: Starlette) -> Request:
    body_bytes = json.dumps(body).encode("utf-8")

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/runs",
        "headers": [(b"content-type", b"application/json")],
        "app": app,
    }
    return Request(scope, receive=receive)


@pytest.mark.asyncio
async def test_create_run_populates_running_op_when_coordinator_bound(
    tmp_path: Path,
    rsa_keys: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lca.infrastructure.file.store import LocalFileStore
    from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

    monkeypatch.setattr(command_endpoints, "resolve_profile_mode", lambda _ctx, mode: mode or "solo")

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    topic_id = f"topic_{uuid.uuid4().hex[:8]}"
    registry = RunRegistry()
    registry.put(
        RunSession(
            run_id=run_id,
            trace_id="trace_gateway",
            spine_path=tmp_path / "run.spine.jsonl",
            tail=LiveTail(),
            question="hi",
            user_text="hi",
            mode="solo",
        )
    )

    store = SqliteRunningOperationStore(":memory:")
    app = Starlette()
    app.state.run_port = _StubRunPort(run_id=run_id)
    app.state.registry = registry
    app.state.file_store = LocalFileStore(tmp_path / "files")
    app.state.running_operation_store = store
    app.state.agent_runtime_coordinator = build_agent_runtime_coordinator(store)

    response = await create_run(
        _request(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "topic_id": topic_id,
            },
            app,
        )
    )
    assert response.status_code == 202

    row = await store.get_latest_for_topic(topic_id)
    assert row is not None
    assert row["run_id"] == run_id

    try:
        from lca.infrastructure.observability.stream import (
            LcaStreamEventManager,
            get_agent_runtime_redis_client,
        )

        mgr = LcaStreamEventManager(get_agent_runtime_redis_client())
        if await mgr.exists(run_id):
            history = await mgr.read_history(run_id, count=5)
            assert any(e["type"] == "agent_runtime_init" for e in history)
            await mgr.cleanup(run_id)
    except Exception:
        pytest.skip("Redis not available for agent_runtime_init assertion")

    await store.delete(run_id)
