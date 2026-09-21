"""EventTranslator unit tests — StampedEvent → AgentStreamEvent.data."""

import json

from lca.application.runtime.coordinator import event_translator
from lca.application.runtime.coordinator.event_translator import (
    EventTranslator,
    wire_tool_call,
)


def test_llm_call_started_becomes_stream_start() -> None:
    t = EventTranslator()
    stamped = {"event": {"type": "LlmCallStarted", "assistantMessage": {"id": "a1"}}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_start"
    assert out["data"]["assistantMessage"]["id"] == "a1"


def test_text_delta_becomes_stream_chunk_text() -> None:
    t = EventTranslator()
    stamped = {"event": {"type": "LlmCallTextDelta", "delta": "hi"}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_chunk"
    assert out["data"]["chunkType"] == "text"
    assert out["data"]["content"] == "hi"
    assert out["data"]["snapshotMode"] == "append"


def test_step_text_delta_answer_channel_becomes_stream_chunk_text() -> None:
    t = EventTranslator()
    stamped = {"event": {"type": "StepTextDelta", "text_delta": "hi", "channel": "answer"}}
    out = t.translate(stamped)
    assert out is not None
    assert out["data"]["chunkType"] == "text"
    assert out["data"]["content"] == "hi"


def test_step_text_delta_decision_channel_is_ignored() -> None:
    t = EventTranslator()
    stamped = {"event": {"type": "StepTextDelta", "text_delta": "secret", "channel": "decision"}}
    assert t.translate(stamped) is None


def test_reasoning_delta_becomes_stream_chunk_reasoning() -> None:
    t = EventTranslator()
    stamped = {"event": {"type": "ReasoningDelta", "text_delta": "thinking"}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_chunk"
    assert out["data"]["chunkType"] == "reasoning"
    assert out["data"]["reasoning"] == "thinking"


def test_spine_llm_call_start_becomes_stream_start_with_parent() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "llm.call.start",
            "parentMessageId": "msg_assistant",
            "payload": {"model": "solo"},
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_start"
    assert out["data"]["assistantMessage"]["id"] == "msg_assistant"


def test_spine_llm_call_end_becomes_stream_end() -> None:
    """Native call_llm publishes stream_end when the model turn finishes.

    LCA must do the same on ``llm.call.end`` so the Thinking block closes and
    the next ``stream_start`` can open a new assistant row instead of wiping
    the previous step's reasoning on the same message.
    """
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "llm.call.end",
            "payload": {"model": "solo", "outcome": "success"},
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_end"


def test_spine_llm_stream_token_reasoning() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "llm.stream.token",
            "payload": {"channel_kind": "reasoning", "text_delta": "plan"},
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["data"]["chunkType"] == "reasoning"
    assert out["data"]["reasoning"] == "plan"


def test_spine_llm_header_assistant_becomes_stream_chunk_text() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "llm.request.header.assistant",
            "assistant_content": "你好呀！",
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_chunk"
    assert out["data"]["chunkType"] == "text"
    assert out["data"]["content"] == "你好呀！"


def test_spine_llm_tool_call_streaming_becomes_tools_calling() -> None:
    """``llm.tool_call.streaming`` 提前渲染原生 ``tools_calling`` 卡片占位。"""
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "llm.tool_call.streaming",
            "payload": {
                "model": "solo",
                "tool_name": "executeCode",
                "invocation_id": "toolu_x",
            },
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_chunk"
    assert out["data"]["chunkType"] == "tools_calling"
    tool = out["data"]["toolsCalling"][0]
    assert tool["id"] == "toolu_x"
    assert tool["apiName"] == "executeCode"


def test_spine_llm_tool_call_streaming_missing_identity_is_ignored() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "llm.tool_call.streaming",
            "payload": {"model": "solo"},
        }
    }
    assert t.translate(stamped) is None


def test_spine_tool_call_record_becomes_tools_calling() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "runCommand",
                "invocation_id": "tc1",
                "arguments": {"command": "echo hi"},
            },
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["data"]["chunkType"] == "tools_calling"
    tools = out["data"]["toolsCalling"]
    assert tools[0]["id"] == "tc1"
    assert tools[0]["apiName"] == "runCommand"
    assert tools[0]["identifier"] == "lobe-cloud-sandbox"
    assert "intervention" not in tools[0]


def test_spine_tool_call_record_pending_approval_carries_intervention_marker() -> None:
    """A gate-blocked call must carry the native ``intervention.status='pending'`` marker
    so LobeHub's getPendingInterventions renders its approval panel."""
    import json

    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "askUserQuestion",
                "invocation_id": "toolu_1",
                "arguments": {
                    "questions": [{"question": "name"}],
                    "lca_run_id": "run_1",
                },
                "status": "pending_approval",
            },
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["data"]["chunkType"] == "tools_calling"
    tools = out["data"]["toolsCalling"]
    assert tools[0]["id"] == "toolu_1"
    assert tools[0]["apiName"] == "askUserQuestion"
    assert tools[0]["identifier"] == "lobe-user-interaction"
    assert tools[0]["intervention"] == {"status": "pending"}
    args = json.loads(tools[0]["arguments"])
    assert args["lca_run_id"] == "run_1"
    assert args["questions"] == [{"question": "name"}]


def test_tool_started_becomes_tool_start_with_parent_message_id() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "type": "ToolStarted",
            "parentMessageId": "m1",
            "payload": {
                "identifier": "lobe-local-system",
                "apiName": "runCommand",
                "arguments": {"command": "ls"},
                "id": "tc1",
            },
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "tool_start"
    assert out["data"]["parentMessageId"] == "m1"
    assert out["data"]["toolCalling"]["identifier"] == "lobe-local-system"


def test_tool_invoked_becomes_tool_end_without_projected_state() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "type": "ToolInvoked",
            "payload": {"toolCalling": {"id": "tc1"}},
            "result": {"content": "ok"},
            "isSuccess": True,
            "executionTime": 120,
            "projected_state": {"stdout": "ok", "exitCode": 0},
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "tool_end"
    assert "projected_state" not in out["data"]  # spec §5.3.1
    assert out["data"]["isSuccess"] is True
    assert out["data"]["result"]["content"] == "ok"
    assert out["data"]["result"]["state"] == {"stdout": "ok", "exitCode": 0}


def test_step_start_with_human_approval_has_requires_approval() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "type": "StepStart",
            "phase": "human_approval",
            "requiresApproval": True,
            "pendingToolsCalling": [{"id": "tc1"}],
        }
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "step_start"
    assert out["data"]["phase"] == "human_approval"
    assert out["data"]["requiresApproval"] is True
    assert out["data"]["pendingToolsCalling"] == [{"id": "tc1"}]


def test_spine_close_with_waiting_human_becomes_agent_runtime_end() -> None:
    """HITL pause emits ``step_start`` + ``agent_runtime_end`` in order (spec §5.2)."""
    t = EventTranslator()
    stamped = {
        "event": {
            "type": "SpineClose",
            "reason": "waiting_for_human",
            "final_state": {"status": "waiting_for_human"},
        }
    }
    out = t.translate(stamped)
    assert isinstance(out, list) and len(out) == 2
    step_start, runtime_end = out
    assert step_start["type"] == "step_start"
    assert step_start["data"]["phase"] == "human_approval"
    assert step_start["data"]["requiresApproval"] is True
    assert step_start["data"]["pendingToolsCalling"] == []
    assert runtime_end["type"] == "agent_runtime_end"
    assert runtime_end["data"]["reason"] == "waiting_for_human"
    assert runtime_end["data"]["finalState"]["status"] == "waiting_for_human"
    assert runtime_end["data"]["phase"] == "execution_complete"


def test_spine_close_with_waiting_input_becomes_step_start_then_runtime_end() -> None:
    t = EventTranslator()
    stamped = {
        "event": {
            "type": "SpineClose",
            "reason": "waiting_input",
            "final_state": {"status": "waiting_input"},
            "pending_tools_calling": [{"id": "tc1"}],
        }
    }
    out = t.translate(stamped)
    assert isinstance(out, list) and len(out) == 2
    assert out[0]["type"] == "step_start"
    assert out[0]["data"]["pendingToolsCalling"] == [{"id": "tc1"}]
    assert out[1]["type"] == "agent_runtime_end"
    assert out[1]["data"]["reason"] == "waiting_input"


def test_spine_close_with_done_becomes_agent_runtime_end_completed() -> None:
    t = EventTranslator()
    stamped = {
        "event": {"type": "SpineClose", "reason": "completed", "final_state": {"status": "done"}}
    }
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "agent_runtime_end"
    assert out["data"]["reason"] == "completed"


def test_unknown_event_returns_none() -> None:
    t = EventTranslator()
    assert t.translate({"event": {"type": "UnknownThing"}}) is None


def test_unknown_event_kind_returns_none() -> None:
    t = EventTranslator()
    assert t.translate({"event": {"type": "LlmCallTextDelta", "kind": "ignore"}}) is None


def test_agent_intervention_request_is_not_emitted_by_lca() -> None:
    """LCA does not produce ``AgentInterventionRequest``.

    The HIL pause round-trip is HTTP-based
    (``POST /lca-api/runs/{runId}/answer`` bridged via
    ``deploy/lobehub/patches/runtime/lca_runtime_agent_gateway.py``), not
    WS-based. The native hetero executor emits ``agent_intervention_request``
    to drive its local CLI/MCP card, but the LCA server-side runtime
    closes the round-trip through the durable journal
    (``approval.persisted.v1`` + ``waiting_input`` checkpoint) plus the
    HTTP answer endpoint — no producer ever fires
    ``kind="AgentInterventionRequest"``.

    Pin this absence so a future refactor cannot silently re-enable a
    wire event with zero consumers in LCA. See
    ``docs/notes/plans/2026-09-16-resume-askuser-flow-audit.md``
    Gap B + Gap G.
    """
    assert "AgentInterventionRequest" not in event_translator._HANDLERS
    assert "AgentInterventionRequest" not in event_translator._SPINE_HANDLERS
    t = EventTranslator()
    assert t.translate({"event": {"type": "AgentInterventionRequest"}}) is None


# ── description fallback (collapsed tool chip must never be empty) ─────────
#
# Front-end RunCommandInspector renders `args.description || args.command`.
# When neither is populated, the chip is empty. LCA's wire_tool_call is the
# sole seam between runtime args and the LobeHub wire shape — guaranteeing a
# non-empty description there keeps the front-end's chip populated for every
# tool, regardless of whether the LLM supplied a description or not.


def test_wire_tool_call_guarantees_non_empty_description() -> None:
    """description defaults to the apiName when caller omits it."""
    wire = wire_tool_call("runCommand", "tc1", {"command": "ls"})
    args = json.loads(wire["arguments"])
    assert args["description"]
    assert args["description"] == "runCommand"
    assert args["command"] == "ls"


def test_wire_tool_call_preserves_explicit_description() -> None:
    """When caller supplies a description, it wins over the default."""
    wire = wire_tool_call(
        "runCommand",
        "tc1",
        {"command": "ls", "description": "List home directory"},
    )
    args = json.loads(wire["arguments"])
    assert args["description"] == "List home directory"


def test_wire_tool_call_falls_back_to_identifier_when_api_name_missing() -> None:
    """Edge: caller passes no tool name. description must still be non-empty."""
    wire = wire_tool_call("", "tc1", {"command": "ls"})
    args = json.loads(wire["arguments"])
    assert args["description"]


def test_wire_tool_call_renames_activate_skill_id_to_name() -> None:
    """RenderContract projects python ``skill_id`` onto inspector ``name``."""
    import lca.infrastructure.tools.skills.activate.tool  # noqa: F401

    wire = wire_tool_call("activate_skill", "tc1", {"skill_id": "officecli"})
    args = json.loads(wire["arguments"])
    assert args["name"] == "officecli"
    assert "skill_id" not in args
    assert args["description"] == "activateSkill"


def test_spine_tool_call_record_passes_description_through_to_wire() -> None:
    """End-to-end: step.tool_call.record → stream_chunk tools_calling chip."""
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "runCommand",
                "invocation_id": "tc1",
                "arguments": {"command": "ls"},  # no description
            },
        }
    }
    out = t.translate(stamped)
    assert out is not None
    args = json.loads(out["data"]["toolsCalling"][0]["arguments"])
    assert args["description"] == "runCommand"


def test_tool_started_event_propagates_description_fallback() -> None:
    """ToolStarted receives a pre-shaped ChatToolPayload — description is set
    upstream by ``session_catalog_map._map_tool_started`` via ``wire_tool_call``,
    so this test pins the contract: the handler preserves whatever it gets.
    """
    t = EventTranslator()
    stamped = {
        "event": {
            "type": "ToolStarted",
            "parentMessageId": "m1",
            "payload": {
                "identifier": "lobe-local-system",
                "apiName": "runCommand",
                "id": "tc1",
                "arguments": json.dumps({"command": "ls", "description": "runCommand"}),
                "type": "builtin",
            },
        }
    }
    out = t.translate(stamped)
    assert out is not None
    args = json.loads(out["data"]["toolCalling"]["arguments"])
    assert args["description"] == "runCommand"


def test_catalog_session_event_tool_started_injects_description() -> None:
    """Catalog path: tool.started.v1 with raw arguments → ChatToolPayload gets
    the description fallback before reaching the translator.
    """
    from lca.application.runtime.coordinator.session_catalog_map import (
        catalog_session_event_to_stamped,
    )

    stamped = catalog_session_event_to_stamped(
        "tool.started.v1",
        {"tool_name": "runCommand", "invocation_id": "tc1", "arguments": {"command": "ls"}},
    )
    assert stamped is not None
    out = EventTranslator().translate(stamped)
    assert out is not None
    args = json.loads(out["data"]["toolCalling"]["arguments"])
    assert args["description"] == "runCommand"


def test_spine_phase_tool_start_empty_payload_returns_none() -> None:
    """Empty-payload ``phase.tool.call.start`` returns ``None``.

    Spine EPs that historically carried only ``state_id`` (legacy
    ``emit_*_for_state`` shape) have no tool identity to translate.
    Returning ``None`` is safe — the gateway treats it as a no-op — and
    prevents a fall-through to ``wire_tool_call("", ...)`` which would
    publish a malformed event if ``SUPPRESSED_SPINE_EPS`` is ever
    relaxed. This contract is shared with ``_spine_body_tool_end`` (see
    ``test_spine_body_tool_end_empty_payload_returns_none``).
    """
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "phase.tool.call.start",
            "payload": {"state_id": "trace_x"},
        }
    }
    assert t.translate(stamped) is None


def test_spine_body_tool_end_empty_payload_returns_none() -> None:
    """Empty-payload ``body.tool.execute.end`` returns ``None``.

    Mirrors the ``_spine_phase_tool_start`` contract: with no
    ``tool_name`` there is no tool identity, so producing a
    ``tool_end`` with ``apiName=""`` / ``id=""`` would be a malformed
    wire. ``SUPPRESSED_SPINE_EPS`` currently filters these out at the
    pump, but the translator must be defensible on its own — see
    ``test_spine_phase_tool_start_empty_payload_returns_none`` for the
    matching rationale.
    """
    t = EventTranslator()
    stamped = {
        "event": {
            "execution_point": "body.tool.execute.end",
            "payload": {"state_id": "trace_x", "outcome": "ok"},
        }
    }
    assert t.translate(stamped) is None
