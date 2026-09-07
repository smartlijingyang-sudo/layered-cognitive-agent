"""Session → gateway pump mapping tests."""

from lca.application.runtime.coordinator.session_gateway_pump import session_event_to_stamped


def test_spine_llm_call_start_maps_execution_point():
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


def test_spine_llm_stream_token_maps_execution_point():
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


def test_thinking_delta_maps_to_reasoning_delta():
    stamped = session_event_to_stamped(
        "thinking.delta.v1",
        {"text_delta": "ponder"},
        assistant_message_id="a1",
    )
    assert stamped == {
        "event": {
            "type": "ReasoningDelta",
            "text_delta": "ponder",
            "parentMessageId": "a1",
        }
    }
