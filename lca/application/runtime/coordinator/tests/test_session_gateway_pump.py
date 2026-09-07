"""Session → gateway pump mapping tests."""

from lca.application.runtime.coordinator.session_gateway_pump import session_event_to_stamped


def test_spine_llm_call_start_maps_execution_point() -> None:
    stamped = session_event_to_stamped(
        "spine.llm.call.start",
        {
            "execution_point": "llm.call.start",
            "payload": {"model": "solo", "stream": True},
        },
        assistant_message_id="msg_assistant",
    )
    assert stamped is not None
    assert stamped["event"]["execution_point"] == "llm.call.start"
    assert stamped["event"]["parentMessageId"] == "msg_assistant"


def test_spine_llm_stream_token_maps_execution_point() -> None:
    stamped = session_event_to_stamped(
        "spine.llm.stream.token",
        {
            "execution_point": "llm.stream.token",
            "channel": "fact",
            "payload": {"channel_kind": "reasoning", "text_delta": "think"},
        },
        assistant_message_id="msg_assistant",
    )
    assert stamped is not None
    assert stamped["event"]["execution_point"] == "llm.stream.token"
    assert stamped["event"]["parentMessageId"] == "msg_assistant"


def test_thinking_delta_is_ignored_when_spine_token_is_ssot() -> None:
    assert (
        session_event_to_stamped(
            "thinking.delta.v1",
            {"text_delta": "ponder"},
            assistant_message_id="a1",
        )
        is None
    )


def test_assistant_responded_is_ignored_when_header_assistant_is_ssot() -> None:
    assert (
        session_event_to_stamped(
            "assistant.responded.v1",
            {"content": "你好"},
            assistant_message_id="a1",
        )
        is None
    )


def test_spine_llm_request_header_assistant_maps_from_session_event_type() -> None:
    """Session append stores category as event.type, not inside data."""
    stamped = session_event_to_stamped(
        "spine.llm.request.header.assistant",
        {
            "step_id": "step-001",
            "assistant_content": "你好呀！",
            "finish_reason": "stop",
        },
        assistant_message_id="msg_assistant",
    )
    assert stamped is not None
    assert stamped["event"]["execution_point"] == "llm.request.header.assistant"
    assert stamped["event"]["assistant_content"] == "你好呀！"
    assert stamped["event"]["parentMessageId"] == "msg_assistant"
