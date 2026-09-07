"""Session catalog → gateway mapping tests."""

from lca.application.runtime.coordinator.session_catalog_map import (
    catalog_session_event_to_stamped,
    is_suppressed_spine_ep,
)
from lca.application.runtime.coordinator.session_gateway_pump import session_event_to_stamped


def test_tool_invoked_v1_maps_with_projected_state():
    stamped = catalog_session_event_to_stamped(
        "tool.invoked.v1",
        {
            "tool_name": "executeCode",
            "invocation_id": "tc_exec_1",
            "ok": True,
            "latency_ms": 42,
            "output_text": "print('joke')",
            "arguments": {"code": "print('joke')", "language": "python"},
            "projected_state": {
                "code": "print('joke')",
                "language": "python",
                "stdout": "Why do programmers...",
            },
        },
        assistant_message_id="msg_a",
    )
    assert stamped is not None
    event = stamped["event"]
    assert event["type"] == "ToolInvoked"
    assert event["projected_state"]["stdout"] == "Why do programmers..."
    assert event["payload"]["toolCalling"]["id"] == "tc_exec_1"
    assert event["parentMessageId"] == "msg_a"


def test_tool_started_v1_maps_to_tool_started():
    stamped = catalog_session_event_to_stamped(
        "tool.started.v1",
        {
            "tool_name": "runCommand",
            "invocation_id": "tc1",
            "arguments": {"command": "echo hi"},
        },
        assistant_message_id="msg_a",
    )
    assert stamped is not None
    assert stamped["event"]["type"] == "ToolStarted"
    assert stamped["event"]["payload"]["apiName"] == "runCommand"
    assert stamped["event"]["payload"]["arguments"] == {"command": "echo hi"}


def test_session_checkpoint_waiting_input_maps_to_spine_close():
    stamped = catalog_session_event_to_stamped(
        "session.checkpoint.v1",
        {"status": "waiting_input"},
    )
    assert stamped is not None
    assert stamped["event"]["type"] == "SpineClose"
    assert stamped["event"]["reason"] == "waiting_for_human"


def test_body_tool_execute_end_spine_is_suppressed():
    assert is_suppressed_spine_ep("body.tool.execute.end")
    assert (
        session_event_to_stamped(
            "spine.body.tool.execute.end",
            {
                "execution_point": "body.tool.execute.end",
                "tool_name": "executeCode",
                "invocation_id": "tc1",
                "outcome": "success",
            },
            assistant_message_id="msg_a",
        )
        is None
    )


def test_catalog_tool_invoked_takes_precedence_over_spine_end():
    """Catalog path must win when both facts exist in the session log."""
    catalog = session_event_to_stamped(
        "tool.invoked.v1",
        {
            "tool_name": "executeCode",
            "invocation_id": "tc1",
            "projected_state": {"stdout": "ok"},
            "ok": True,
        },
        assistant_message_id="msg_a",
    )
    assert catalog is not None
    assert catalog["event"]["type"] == "ToolInvoked"
