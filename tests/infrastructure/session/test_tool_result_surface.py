"""ADR-0201 tool result → model-visible message projection."""

from __future__ import annotations

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.infrastructure.session.context.model_context_assembler import DefaultModelContextAssembler
from lca.infrastructure.session.emit.tool_surface_emit import append_tool_result_surface
from lca.infrastructure.session.projections.tool_result_message import (
    build_tool_surface_data,
    observation_tool_result_content,
)
from lca.plugins.events.publishers._session_publish import reset_publish_session, set_publish_session
from lca.plugins.session.projection_registry.projection_registry import ProjectionRegistry
from lca.plugins.session.runtime.messages.messages import derive_messages
from lca.plugins.session.session_model_visible.session_model_visible import ModelVisibleUnit
from lca.session.append import Session
from lca.session.lifecycle.bind import RunEventSessionBridge
from lca_kernel.events.fold.fold import SURFACE_ASSISTANT_TYPE, SURFACE_TOOL_RESULT_TYPE, SURFACE_USER_TYPE


def test_observation_tool_result_content_success_stdout() -> None:
    obs = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"stdout": "hello pdf"},
    )
    assert observation_tool_result_content(obs) == "hello pdf"


def test_observation_tool_result_content_failure() -> None:
    obs = Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error="exit_code=127",
    )
    assert "127" in observation_tool_result_content(obs)


def test_build_tool_surface_data_includes_openai_message() -> None:
    obs = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"content": "page 1"},
    )
    data = build_tool_surface_data(
        tool_name="runCommand",
        invocation_id="call-1",
        attempt=1,
        outcome="success",
        observation=obs,
    )
    assert data["message"]["role"] == "tool"
    assert data["message"]["tool_call_id"] == "call-1"
    assert data["message"]["content"] == "page 1"


def test_assemble_model_history_includes_tool_after_surface_append() -> None:
    registry = ProjectionRegistry()
    registry.register(ModelVisibleUnit())
    session = Session("tool_surface_1")
    registry.register_to(session)
    session.append(SURFACE_USER_TYPE, {"content": "analyze file"}, surface_op="append")
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "runCommand", "arguments": "{}"},
                    }
                ],
            }
        },
        surface_op="append",
    )
    session.append(
        SURFACE_TOOL_RESULT_TYPE,
        build_tool_surface_data(
            tool_name="runCommand",
            invocation_id="call-1",
            attempt=1,
            outcome="success",
            observation=Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={"stdout": "extracted text"},
            ),
        ),
        surface_op="append",
    )
    expected = derive_messages(session.snapshot_events())
    assembled = DefaultModelContextAssembler().assemble(session, step=2)
    assert assembled.messages == expected
    tool_msgs = [m for m in assembled.messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "call-1"
    assert "extracted text" in str(tool_msgs[0]["content"])


def test_append_tool_result_surface_unwraps_bridge() -> None:
    session = Session("tool_surface_bridge")
    bridge = RunEventSessionBridge(session)
    token = set_publish_session(bridge)
    try:
        receipt = append_tool_result_surface(
            tool_name="runCommand",
            invocation_id="call-bridge-1",
            attempt=1,
            outcome="success",
            observation=Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={"stdout": "pdf text"},
            ),
        )
        assert receipt is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == SURFACE_TOOL_RESULT_TYPE
        assert event.actor == "body"
    finally:
        reset_publish_session(token)
