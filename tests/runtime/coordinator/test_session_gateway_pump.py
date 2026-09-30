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
    assert stamped["event"]["stream"] is True


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


def test_unknown_event_type_without_execution_point_returns_none() -> None:
    assert session_event_to_stamped("custom.event.v1", {"foo": "bar"}) is None


def test_non_spine_event_with_execution_point_maps() -> None:
    stamped = session_event_to_stamped(
        "custom.event.v1",
        {"execution_point": "custom.ep", "payload": {"value": 1}},
        assistant_message_id="msg_a",
    )
    assert stamped is not None
    assert stamped["event"]["execution_point"] == "custom.ep"
    assert stamped["event"]["type"] == "custom.ep"
    assert stamped["event"]["value"] == 1
    assert stamped["event"]["parentMessageId"] == "msg_a"


def test_spine_event_without_execution_point_derives_ep_from_category() -> None:
    """``spine.*`` events without a stored execution_point get one via category."""
    stamped = session_event_to_stamped(
        "spine.skill.package.activated",
        {"payload": {"package_name": "web-search"}},
    )
    assert stamped is not None
    assert stamped["event"]["execution_point"] == "skill.package.activated"
    assert stamped["event"]["type"] == "skill.package.activated"
    assert stamped["event"]["package_name"] == "web-search"


def test_suppressed_spine_ep_returns_none() -> None:
    """Spine EPs superseded by catalog lifecycle facts must not be republished."""
    stamped = session_event_to_stamped(
        "spine.body.tool.execute.end",
        {"execution_point": "body.tool.execute.end", "payload": {"ok": True}},
    )
    assert stamped is None


def test_catalog_event_takes_precedence_over_converter() -> None:
    """Catalog lifecycle facts map through the catalog tier, not the converter."""
    stamped = session_event_to_stamped("tool.started.v1", {"tool": "read_file"})
    assert stamped is not None
    assert "type" in stamped["event"]


def test_spine_event_payload_category_overrides_to_header_assistant() -> None:
    """Payload category ``spine.llm.request.header.assistant`` wins the EP."""
    stamped = session_event_to_stamped(
        "spine.some.event",
        {"payload": {"category": "spine.llm.request.header.assistant", "content": "hi"}},
    )
    assert stamped is not None
    assert stamped["event"]["execution_point"] == "llm.request.header.assistant"


def test_spine_event_with_data_category_overrides() -> None:
    """A top-level ``category`` field also drives the header-assistant override."""
    stamped = session_event_to_stamped(
        "spine.other.event",
        {"category": "spine.llm.request.header.assistant", "content": "hello"},
    )
    assert stamped is not None
    assert stamped["event"]["execution_point"] == "llm.request.header.assistant"


def test_strategy_map_is_table_driven() -> None:
    """The converter dispatch must be a table, not a growing if-chain."""
    from lca.application.runtime.coordinator.session_gateway_pump import _EVENT_CONVERTERS

    assert "thinking.delta.v1" in _EVENT_CONVERTERS
    assert "assistant.responded.v1" in _EVENT_CONVERTERS
    # The generic execution-point converter is the fallback, not a table key.
    assert "spine.llm.stream.token" not in _EVENT_CONVERTERS
