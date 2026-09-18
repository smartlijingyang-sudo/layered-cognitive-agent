"""Session catalog → gateway mapping tests."""

from lca.application.runtime.coordinator.session_catalog_map import (
    catalog_session_event_to_stamped,
    is_suppressed_spine_ep,
)
from lca.application.runtime.coordinator.session_gateway_pump import session_event_to_stamped


def test_tool_invoked_v1_maps_with_projected_state() -> None:
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


def test_tool_started_v1_maps_to_tool_started() -> None:
    import json

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
    # arguments is JSON-encoded per wire_tool_call contract; description is
    # auto-injected so the front-end chip is never blank.
    args = json.loads(stamped["event"]["payload"]["arguments"])
    assert args == {"command": "echo hi", "description": "runCommand"}


def test_tool_started_v1_preserves_caller_supplied_description() -> None:
    import json

    stamped = catalog_session_event_to_stamped(
        "tool.started.v1",
        {
            "tool_name": "runCommand",
            "invocation_id": "tc1",
            "arguments": {"command": "echo hi", "description": "Custom label"},
        },
        assistant_message_id="msg_a",
    )
    assert stamped is not None
    args = json.loads(stamped["event"]["payload"]["arguments"])
    assert args["description"] == "Custom label"


def test_session_checkpoint_waiting_input_maps_to_spine_close() -> None:
    stamped = catalog_session_event_to_stamped(
        "session.checkpoint.v1",
        {"status": "waiting_input"},
    )
    assert stamped is not None
    assert stamped["event"]["type"] == "SpineClose"
    assert stamped["event"]["reason"] == "waiting_for_human"


def test_session_checkpoint_forwards_pending_tools_calling_when_present() -> None:
    """HITL card data flows through when the checkpoint carries it; absent → omitted."""
    stamped = catalog_session_event_to_stamped(
        "session.checkpoint.v1",
        {"status": "waiting_input", "pending_tools_calling": [{"id": "tc1"}]},
    )
    assert stamped is not None
    assert stamped["event"]["pending_tools_calling"] == [{"id": "tc1"}]

    bare = catalog_session_event_to_stamped(
        "session.checkpoint.v1",
        {"status": "waiting_input"},
    )
    assert bare is not None
    assert "pending_tools_calling" not in bare["event"]


def test_session_checkpoint_dataclass_pending_tools_flows_to_step_start() -> None:
    """The ``SessionCheckpoint`` field reaches the WS ``step_start`` pause pair."""
    from dataclasses import asdict

    from lca.application.runtime.coordinator.event_translator import EventTranslator
    from lca.contracts.harness.memory.events import SessionCheckpoint

    checkpoint = SessionCheckpoint(
        status="waiting_input",
        pending_tools_calling=[
            {
                "tool_name": "askUserQuestion",
                "call_id": "toolu_1",
                "arguments": {"questions": []},
            }
        ],
    )
    stamped = catalog_session_event_to_stamped(
        "session.checkpoint.v1",
        asdict(checkpoint),
    )
    assert stamped is not None
    assert stamped["event"]["pending_tools_calling"] == [
        {
            "tool_name": "askUserQuestion",
            "call_id": "toolu_1",
            "arguments": {"questions": []},
        }
    ]
    out = EventTranslator().translate(stamped)
    assert isinstance(out, list)
    step_start = out[0]
    assert step_start["type"] == "step_start"
    assert step_start["data"]["phase"] == "human_approval"
    assert step_start["data"]["requiresApproval"] is True
    assert step_start["data"]["pendingToolsCalling"] == [
        {
            "tool_name": "askUserQuestion",
            "call_id": "toolu_1",
            "arguments": {"questions": []},
        }
    ]


def test_body_tool_execute_end_spine_is_suppressed() -> None:
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


def test_catalog_tool_invoked_takes_precedence_over_spine_end() -> None:
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


def test_approval_persisted_is_ws_silent() -> None:
    """``approval.persisted.v1`` stays journal-internal (recovery SSOT).

    It always pairs with a ``waiting_input`` checkpoint that already
    yields the WS pause pair; mapping both double-publishes.
    """
    assert (
        catalog_session_event_to_stamped(
            "approval.persisted.v1",
            {"approval_id": "a1", "resume_point": {}},
        )
        is None
    )
