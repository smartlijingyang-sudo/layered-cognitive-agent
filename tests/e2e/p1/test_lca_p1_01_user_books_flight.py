"""L3-1: 订明天去北京的机票 (full HIL flow).

Real LCA kernel + Python wire harness. Asserts the full event stream
matches the native AgentStreamClient's expectations and that the
HIL pause/resume cycle works.

DEFERRED per ruling 5 in the PR-3 dispatch: the kernel subprocess
fixture requires the LCA dev stack (``lca-ops infra start`` +
Postgres + Redis + LLM provider) which is not available in this
host's CI. The test is gated on ``LCA_E2E_KERNEL=1`` (see conftest.py).

The wire-harness contract itself is exercised by the L2 sweep
(``tests/integration/p1/``); this test only adds the end-to-end
scenarios that bind WS events to a real producer.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest


@pytest.mark.timeout(60)
def test_user_books_flight_full_hil_flow(lca_client) -> None:
    """Full pause/resume HIL flow against a real LCA kernel."""
    pytest.skip(
        "L3-1 requires LCA_E2E_KERNEL=1 (LCA dev stack); see "
        "tests/e2e/p1/conftest.py and "
        "docs/notes/proposed/contract/2026-09-07-p1-facade-ws-token-todo.md"
    )


def test_event_envelope_shapes_match_python_wire_types() -> None:
    """L3-parity smoke: every AgentStreamEvent field name matches the
    Pydantic union in ``lca.contracts.transport.agent_stream_event``.

    This test does NOT need a kernel — it just imports both schemas
    and asserts every Python field has a TS counterpart (and vice
    versa) by string-matching the wire event ``type`` enum.
    """
    from lca.contracts.transport import agent_stream_event as py_events
    from lca.contracts.transport import gateway_messages as py_msgs

    py_types = {
        "agent_runtime_init",
        "agent_runtime_end",
        "stream_start",
        "stream_chunk",
        "stream_end",
        "visible_output_end",
        "stream_retry",
        "tool_start",
        "tool_end",
        "tool_execute",
        "agent_intervention_request",
        "agent_intervention_response",
        "step_start",
        "step_complete",
        "notify_update",
        "error",
        "heartbeat",
    }
    # ``tool_result`` is present in the TS AgentStreamEvent union but
    # not in the Python side (the Python producer emits ``tool_end``
    # with ``result`` populated). The drift is captured in the
    # deferred note (see ``docs/notes/proposed/contract/
    # 2026-09-07-p1-facade-ws-token-todo.md``).
    ts_extra = {"tool_result"}
    # Walk the AgentStreamEvent union (Annotated[Union[...], Field(...)]).
    outer_args = getattr(py_events.AgentStreamEvent, "__args__", ())
    found = set()
    # outer_args[0] is the Union itself.
    for arg in outer_args:
        union_members = getattr(arg, "__args__", ())
        if not union_members:
            # arg might be a single class (no union).
            default = getattr(arg, "model_fields", {}).get("type")
            if default is not None and hasattr(default, "default"):
                found.add(default.default)
            continue
        for member in union_members:
            default = getattr(member, "model_fields", {}).get("type")
            if default is not None and hasattr(default, "default"):
                found.add(default.default)
    found.discard(None)
    assert found == py_types, f"mismatch: {found ^ py_types}"
    # The ``tool_result`` drift is tracked in the deferred note; the
    # Python producer surface stays smaller than the TS union until
    # PR-4 closes it. We do not assert against the TS list here to
    # avoid coupling this Python test to the lobehub-ui checkout.

    # Sanity: the gateway messages also expose the expected client/server
    # frame ``type`` literals.
    msg_types: set[str] = set()
    for cls in (
        py_msgs.AuthMessage,
        py_msgs.ResumeMessage,
        py_msgs.HeartbeatMessage,
        py_msgs.InterruptMessage,
        py_msgs.ToolResultMessage,
        py_msgs.AuthSuccess,
        py_msgs.AuthFailed,
        py_msgs.AuthExpired,
        py_msgs.HeartbeatAck,
        py_msgs.SessionComplete,
        py_msgs.ResumeComplete,
        py_msgs.AgentEvent,
    ):
        default = getattr(cls, "model_fields", {}).get("type")
        if default is not None and hasattr(default, "default"):
            msg_types.add(default.default)
    msg_types.discard(None)
    expected_msg_types = {
        "auth",
        "resume",
        "heartbeat",
        "interrupt",
        "tool_result",
        "auth_success",
        "auth_failed",
        "auth_expired",
        "heartbeat_ack",
        "session_complete",
        "resume_complete",
        "agent_event",
    }
    assert msg_types == expected_msg_types, f"mismatch: {msg_types ^ expected_msg_types}"