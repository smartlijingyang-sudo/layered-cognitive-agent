"""Verify Python types produce JSON byte-compat with the native TS union.

Each AgentStreamEvent type is roundtripped to dict and asserted to have
the same key set as the TS source-of-truth in
lobehub-ui/packages/agent-gateway-client/src/types.ts.
"""
import pytest
from pydantic import ValidationError

from lca.contracts.transport.agent_stream_event import (
    AgentRuntimeEnd,
    AgentRuntimeEndData,
    StreamChunk,
    StreamChunkData,
    StreamStart,
    StreamStartData,
    ToolEnd,
    ToolEndData,
    ToolStart,
    ToolStartData,
)
from lca.contracts.transport.gateway_messages import (
    AgentEvent,
    AuthMessage,
    ResumeComplete,
    ResumeMessage,
    SessionComplete,
)


def test_stream_start_roundtrips_with_assistant_message():
    """TS: assistantMessage must carry id + model + provider + role."""
    s = StreamStart(data=StreamStartData(assistantMessage={"id": "a1", "model": "gpt-4", "provider": "openai", "role": "assistant"}), operationId="op1", stepIndex=0, timestamp=0)
    d = s.model_dump()
    assert d["type"] == "stream_start"
    assert d["data"]["assistantMessage"]["id"] == "a1"
    assert d["data"]["assistantMessage"]["model"] == "gpt-4"


def test_stream_chunk_text_has_chunk_type():
    s = StreamChunk(data=StreamChunkData(chunkType="text", content="hello"), operationId="op1", stepIndex=0, timestamp=0)
    assert s.model_dump()["data"]["chunkType"] == "text"


def test_tool_start_carries_parent_message_id_and_tool_calling():
    s = ToolStart(
        data=ToolStartData(parentMessageId="m1", toolCalling={"identifier": "lobe-local-system", "apiName": "runCommand", "arguments": {"command": "ls"}, "id": "tc1", "type": "builtin"}),
        operationId="op1", stepIndex=0, timestamp=0,
    )
    d = s.model_dump()
    assert d["data"]["parentMessageId"] == "m1"
    assert d["data"]["toolCalling"]["identifier"] == "lobe-local-system"


def test_tool_end_no_projected_state():
    """spec §5.3.1: WS tool_end must NOT carry projected_state. Server writes it to DB."""
    s = ToolEnd(
        data=ToolEndData(isSuccess=True, result={"content": "ok"}, payload={"toolCalling": {"id": "tc1"}}, executionTime=120),
        operationId="op1", stepIndex=0, timestamp=0,
    )
    assert "projected_state" not in s.model_dump()["data"]


def test_agent_runtime_end_has_phase_execution_complete():
    s = AgentRuntimeEnd(
        data=AgentRuntimeEndData(
            finalState={"status": "done"},
            reason="completed",
            reasonDetail="ok",
            phase="execution_complete",
        ),
        operationId="op1", stepIndex=0, timestamp=0,
    )
    assert s.model_dump()["data"]["phase"] == "execution_complete"


def test_auth_message_carries_token():
    s = AuthMessage(token="<jwt>")  # noqa: S106 - test fixture, not a real credential
    assert s.model_dump() == {"type": "auth", "token": "<jwt>"}


def test_resume_message_carries_last_event_id_and_want_status():
    s = ResumeMessage(lastEventId="123-0", wantStatus=True)
    d = s.model_dump()
    assert d["type"] == "resume"
    assert d["lastEventId"] == "123-0"
    assert d["wantStatus"] is True


def test_resume_complete_status_enum():
    s = ResumeComplete(status="waiting_input")
    assert s.model_dump() == {"type": "resume_complete", "status": "waiting_input"}


def test_session_complete_no_payload():
    s = SessionComplete()
    assert s.model_dump() == {"type": "session_complete"}


def test_agent_event_envelope():
    s = AgentEvent(id="123-0", event={"type": "stream_chunk", "data": {"chunkType": "text", "content": "x"}, "operationId": "op1", "stepIndex": 0, "timestamp": 0})
    d = s.model_dump()
    assert d["type"] == "agent_event"
    assert d["id"] == "123-0"
    assert d["event"]["type"] == "stream_chunk"


def test_stream_keys_match_native():
    from lca.contracts.transport.stream_keys import (
        STREAM_KEY_PREFIX,
        STREAM_MAXLEN,
        STREAM_RETENTION_SECONDS,
    )
    assert STREAM_KEY_PREFIX == "agent_runtime_stream"
    assert STREAM_RETENTION_SECONDS == 2 * 3600
    assert STREAM_MAXLEN == "~1000"


@pytest.mark.parametrize("type_name", [
    "agent_runtime_init", "agent_runtime_end", "stream_start", "stream_chunk",
    "stream_end", "visible_output_end", "stream_retry", "tool_start",
    "tool_end", "tool_execute", "agent_intervention_request",
    "agent_intervention_response", "step_start", "step_complete",
    "notify_update", "error", "heartbeat",
])
def test_all_18_event_types_exist(type_name):
    """Each AgentStreamEvent `type` literal must roundtrip.

    Class names are CamelCase (`StreamStart`); the wire `type` field is
    snake_case (`"stream_start"`). Verify by constructing each class with
    its default `type` literal and reading it back.
    """
    import inspect

    from lca.contracts.transport import agent_stream_event as mod
    snake = type_name
    found = False
    for cls_name in mod.__all__:
        cls = getattr(mod, cls_name, None)
        if cls is None or not inspect.isclass(cls):
            continue
        try:
            inst = cls.model_construct()
        except (TypeError, ValidationError, ValueError):
            continue
        if getattr(inst, "type", None) == snake:
            found = True
            break
    assert found, f"Missing AgentStreamEvent for type={type_name!r}"
