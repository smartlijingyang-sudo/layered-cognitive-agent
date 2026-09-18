"""L2-9: ``POST /v1/runs`` forwards ``resume_tool_result`` to ``RunPort.resume_approval``.

Gap C: the LCA front-end ``LcaStartRunBody`` declares ``resume_tool_result``
with fields ``{content, parentMessageId, toolCallId, pluginState}``
(deploy/lobehub/patches/runtime/lcaGateway/execute.ts:31-36). Before this
fix the back-end ``decode_create_run`` silently dropped the field, so a
resume POSTed to ``/v1/runs`` with ``resume_tool_result`` arrived at
``create_and_dispatch`` (a fresh run) instead of routing to the existing
paused run via ``resume_approval``.

This test asserts the back-end accepts the body and forwards all four
fields — including ``pluginState`` — to the run port, so the existing
paused run resumes from ``phase: 'tool_result'``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request

from lca.infrastructure.observability.running_operation_store import (
    SqliteRunningOperationStore,
)
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    create_run,
)


class _RecordingPort:
    """Captures every call to ``resume_approval`` for assertion."""

    def __init__(self) -> None:
        self.create_calls: list[Any] = []
        self.resume_calls: list[dict[str, Any]] = []

    async def create_and_dispatch(self, request: Any) -> Any:
        from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
            RunReceipt,
        )

        self.create_calls.append(request)
        return RunReceipt(
            run_id="run_unused",
            trace_id="trace_unused",
            accepted=True,
            rejection_reason=None,
        )

    async def resume_approval(
        self,
        run_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
        *,
        plugin_state: dict[str, Any] | None = None,
        parent_message_id: str = "",
    ) -> Any:
        from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import (
            RunCommandReceipt,
        )

        self.resume_calls.append(
            {
                "run_id": run_id,
                "approval_id": approval_id,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "plugin_state": plugin_state,
                "parent_message_id": parent_message_id,
            }
        )
        return RunCommandReceipt(accepted=True, status="resumed")


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


@pytest.fixture
def mock_mode_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip real Profile/mode registry resolution in unit tests."""
    from lca.plugins.transport.webserver.handlers.runs.api import command_endpoints

    monkeypatch.setattr(
        command_endpoints, "resolve_profile_mode", lambda _ctx, mode: mode or "solo"
    )


@pytest.mark.asyncio
async def test_post_runs_with_resume_tool_result_forwards_to_run_port(
    tmp_path: Path,
    rsa_keys: dict[str, str],
    mock_mode_resolver: None,
) -> None:
    """``resume_tool_result`` POSTed to /v1/runs is routed to ``resume_approval``.

    Verifies the four front-end fields land on the port:
    - ``toolCallId`` ⇒ ``approval_id``
    - ``content`` ⇒ ``payload``
    - ``pluginState`` ⇒ ``plugin_state``
    - ``parentMessageId`` ⇒ ``parent_message_id``
    """
    from lca.infrastructure.file.store import LocalFileStore

    run_id = "run_existing_paused"
    topic_id = "topic_resume_a"
    store = SqliteRunningOperationStore(":memory:")
    await store.insert(
        run_id=run_id,
        topic_id=topic_id,
        agent_id="agent_a",
        assistant_message_id="msg_parent",
        scope="main",
    )

    port = _RecordingPort()
    app = Starlette()
    app.state.ctx = object()
    app.state.file_store = LocalFileStore(tmp_path / "files")
    app.state.run_port = port
    app.state.running_operation_store = store

    response = await create_run(
        _request(
            {
                "messages": [{"role": "user", "content": "answer"}],
                "topic_id": topic_id,
                "resume_tool_result": {
                    "toolCallId": "tc_42",
                    "parentMessageId": "msg_parent",
                    "content": "the user's answer",
                    "pluginState": {"askUserAnswers": {"q1": "a"}},
                },
            },
            app,
        )
    )
    assert response.status_code == 200
    assert port.create_calls == [], "resume_tool_result must skip create_and_dispatch"
    assert len(port.resume_calls) == 1
    call = port.resume_calls[0]
    assert call["run_id"] == run_id
    assert call["approval_id"] == "tc_42"
    assert call["payload"] == "the user's answer"
    assert call["plugin_state"] == {"askUserAnswers": {"q1": "a"}}
    assert call["parent_message_id"] == "msg_parent"
    assert call["idempotency_key"], "idempotency_key must be derived from toolCallId"


@pytest.mark.asyncio
async def test_post_runs_with_resume_tool_result_accepts_empty_messages(
    tmp_path: Path,
    rsa_keys: dict[str, str],
    mock_mode_resolver: None,
) -> None:
    """A resume body carries no user prompt: empty ``messages`` must not 400.

    The LCA resume op (``lcaResumeGatewayRun``) POSTs ``/lca-api/runs`` with
    ``messages: []`` plus ``resume_tool_result``. The non-empty user-message
    validation applies to fresh runs only; a resume already has its run
    context server-side and would otherwise be rejected before routing.
    """
    from lca.infrastructure.file.store import LocalFileStore

    run_id = "run_existing_paused_empty"
    topic_id = "topic_resume_empty"
    store = SqliteRunningOperationStore(":memory:")
    await store.insert(
        run_id=run_id,
        topic_id=topic_id,
        agent_id="agent_a",
        assistant_message_id="msg_parent",
        scope="main",
    )

    port = _RecordingPort()
    app = Starlette()
    app.state.ctx = object()
    app.state.file_store = LocalFileStore(tmp_path / "files")
    app.state.run_port = port
    app.state.running_operation_store = store

    response = await create_run(
        _request(
            {
                "messages": [],
                "topic_id": topic_id,
                "resume_tool_result": {
                    "toolCallId": "tc_empty",
                    "parentMessageId": "msg_parent",
                    "content": "the user's answer",
                },
            },
            app,
        )
    )
    assert response.status_code == 200
    assert port.create_calls == [], "resume_tool_result must skip create_and_dispatch"
    assert len(port.resume_calls) == 1
    call = port.resume_calls[0]
    assert call["run_id"] == run_id
    assert call["approval_id"] == "tc_empty"
    assert call["payload"] == "the user's answer"


@pytest.mark.asyncio
async def test_post_runs_without_resume_field_still_creates_run(
    tmp_path: Path,
    rsa_keys: dict[str, str],
    mock_mode_resolver: None,
) -> None:
    """Regression: bodies without ``resume_*`` keep the create-and-dispatch path."""
    from lca.infrastructure.file.store import LocalFileStore

    port = _RecordingPort()
    app = Starlette()
    app.state.ctx = object()
    app.state.file_store = LocalFileStore(tmp_path / "files")
    app.state.run_port = port

    response = await create_run(
        _request(
            {"messages": [{"role": "user", "content": "hi"}]},
            app,
        )
    )
    assert response.status_code == 202
    assert len(port.create_calls) == 1
    assert port.resume_calls == []


@pytest.mark.asyncio
async def test_post_runs_with_resume_tool_result_rejects_missing_topic(
    tmp_path: Path,
    rsa_keys: dict[str, str],
    mock_mode_resolver: None,
) -> None:
    """Resume bodies without ``topic_id`` fail closed (no run to look up)."""
    from lca.infrastructure.file.store import LocalFileStore
    from lca.infrastructure.observability.running_operation_store import (
        SqliteRunningOperationStore,
    )

    port = _RecordingPort()
    app = Starlette()
    app.state.ctx = object()
    app.state.file_store = LocalFileStore(tmp_path / "files")
    app.state.run_port = port
    app.state.running_operation_store = SqliteRunningOperationStore(":memory:")

    response = await create_run(
        _request(
            {
                "messages": [{"role": "user", "content": "answer"}],
                "resume_tool_result": {
                    "toolCallId": "tc_1",
                    "parentMessageId": "msg1",
                    "content": "user answered",
                },
            },
            app,
        )
    )
    assert response.status_code == 400
    assert port.create_calls == []
    assert port.resume_calls == []


@pytest.mark.asyncio
async def test_decode_create_run_normalizes_resume_tool_result_payload(
    tmp_path: Path,
) -> None:
    """Unit-level: ``decode_create_run`` extracts all four front-end fields.

    Decoupled from the Starlette path so the regression covers shape and
    camelCase/snake_case normalization without the coordinator / JWT setup.
    """
    from lca.infrastructure.file.store import LocalFileStore
    from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
        decode_create_run,
    )

    file_store = LocalFileStore(tmp_path / "files")
    decoded = await decode_create_run(
        {
            "messages": [{"role": "user", "content": "hi"}],
            "resume_tool_result": {
                "toolCallId": "tc_42",
                "parentMessageId": "msg_parent",
                "content": "user answer",
                "pluginState": {"askUserAnswers": {"q1": "a"}},
            },
        },
        ctx=object(),
        file_store=file_store,
        resolve_mode=lambda _ctx, mode: mode or "solo",
    )
    assert not hasattr(decoded, "status_code")  # not a JSONResponse
    assert isinstance(decoded.resume_tool_result, dict)
    assert decoded.resume_tool_result["tool_call_id"] == "tc_42"
    assert decoded.resume_tool_result["parent_message_id"] == "msg_parent"
    assert decoded.resume_tool_result["content"] == "user answer"
    assert decoded.resume_tool_result["plugin_state"] == {"askUserAnswers": {"q1": "a"}}
    assert decoded.resume_approval is None


@pytest.mark.asyncio
async def test_decode_create_run_rejects_malformed_resume_tool_result(
    tmp_path: Path,
) -> None:
    """Resume bodies with a non-object ``resume_tool_result`` return 400."""
    from lca.infrastructure.file.store import LocalFileStore
    from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
        decode_create_run,
    )

    file_store = LocalFileStore(tmp_path / "files")
    decoded = await decode_create_run(
        {
            "messages": [{"role": "user", "content": "hi"}],
            "resume_tool_result": "not an object",
        },
        ctx=object(),
        file_store=file_store,
        resolve_mode=lambda _ctx, mode: mode or "solo",
    )
    assert decoded.status_code == 400
