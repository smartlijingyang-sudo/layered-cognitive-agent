from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from lca.infrastructure.file.store import LocalFileStore
from lca.plugins.transport.webserver.handlers.runs.api.command_endpoints import (
    CreateRunRequest,
    _dispatch_resume,
    decode_create_run,
)


@pytest.mark.asyncio
async def test_decode_create_run_extracts_run_id(tmp_path: Path) -> None:
    file_store = LocalFileStore(tmp_path / "files")
    decoded = await decode_create_run(
        {
            "run_id": "run_explicit_456",
            "messages": [{"role": "user", "content": "hello"}],
            "resume_tool_result": {
                "toolCallId": "tc_42",
                "parentMessageId": "msg_parent",
                "content": "user answer",
            },
        },
        ctx=object(),
        file_store=file_store,
        resolve_mode=lambda _ctx, mode: mode or "solo",
    )
    assert not hasattr(decoded, "status_code")
    assert isinstance(decoded, CreateRunRequest)
    assert decoded.run_id == "run_explicit_456"


@pytest.mark.asyncio
async def test_dispatch_resume_prefers_explicit_run_id() -> None:
    request = MagicMock(spec=Request)
    run_port = MagicMock()
    run_port.resume_approval = AsyncMock(
        return_value=MagicMock(accepted=True, status="resumed", error=None, error_status=200)
    )
    request.app.state.run_port = run_port

    store = MagicMock()
    store.get_latest_for_topic = AsyncMock(return_value={"run_id": "wrong_run_id"})
    store.record_answer_key = AsyncMock()
    request.app.state.running_operation_store = store

    body = {
        "run_id": "target_run_123",
        "topic_id": "tpc_abc",
        "resume_tool_result": {
            "toolCallId": "toolu_xyz",
            "content": "user answer",
            "parentMessageId": "msg_001",
        },
    }
    decoded = MagicMock(spec=CreateRunRequest)
    decoded.run_id = "target_run_123"
    decoded.resume_approval = None
    decoded.resume_tool_result = {
        "tool_call_id": "toolu_xyz",
        "content": "user answer",
        "parent_message_id": "msg_001",
        "plugin_state": None,
    }

    res = await _dispatch_resume(request, body, decoded)
    assert res.status_code == 200
    store.get_latest_for_topic.assert_not_called()
    run_port.resume_approval.assert_awaited_once()
    assert run_port.resume_approval.call_args[0][0] == "target_run_123"


@pytest.mark.asyncio
async def test_dispatch_resume_falls_back_to_topic_when_no_run_id() -> None:
    request = MagicMock(spec=Request)
    run_port = MagicMock()
    run_port.resume_approval = AsyncMock(
        return_value=MagicMock(accepted=True, status="resumed", error=None, error_status=200)
    )
    request.app.state.run_port = run_port

    store = MagicMock()
    store.get_latest_for_topic = AsyncMock(return_value={"run_id": "fallback_run_999"})
    store.record_answer_key = AsyncMock()
    request.app.state.running_operation_store = store

    body = {
        "topic_id": "tpc_abc",
        "resume_tool_result": {
            "toolCallId": "toolu_xyz",
            "content": "user answer",
            "parentMessageId": "msg_001",
        },
    }
    decoded = MagicMock(spec=CreateRunRequest)
    decoded.run_id = ""
    decoded.resume_approval = None
    decoded.resume_tool_result = {
        "tool_call_id": "toolu_xyz",
        "content": "user answer",
        "parent_message_id": "msg_001",
        "plugin_state": None,
    }

    res = await _dispatch_resume(request, body, decoded)
    assert res.status_code == 200
    store.get_latest_for_topic.assert_awaited_once_with("tpc_abc")
    run_port.resume_approval.assert_awaited_once()
    assert run_port.resume_approval.call_args[0][0] == "fallback_run_999"
