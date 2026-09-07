"""EventTranslator unit tests — StampedEvent → AgentStreamEvent.data."""

from lca.application.runtime.coordinator.event_translator import EventTranslator


def test_llm_call_started_becomes_stream_start():
    t = EventTranslator()
    stamped = {"event": {"type": "LlmCallStarted", "assistantMessage": {"id": "a1"}}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_start"
    assert out["data"]["assistantMessage"]["id"] == "a1"


def test_text_delta_becomes_stream_chunk_text():
    t = EventTranslator()
    stamped = {"event": {"type": "LlmCallTextDelta", "delta": "hi"}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_chunk"
    assert out["data"]["chunkType"] == "text"
    assert out["data"]["content"] == "hi"
    assert out["data"]["snapshotMode"] == "append"


def test_reasoning_delta_becomes_stream_chunk_reasoning():
    t = EventTranslator()
    stamped = {"event": {"type": "ReasoningDelta", "delta": "thinking"}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "stream_chunk"
    assert out["data"]["chunkType"] == "reasoning"
    assert out["data"]["content"] == "thinking"


def test_tool_started_becomes_tool_start_with_parent_message_id():
    t = EventTranslator()
    stamped = {"event": {"type": "ToolStarted", "parentMessageId": "m1", "payload": {"identifier": "lobe-local-system", "apiName": "runCommand", "arguments": {"command": "ls"}, "id": "tc1"}}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "tool_start"
    assert out["data"]["parentMessageId"] == "m1"
    assert out["data"]["toolCalling"]["identifier"] == "lobe-local-system"


def test_tool_invoked_becomes_tool_end_without_projected_state():
    t = EventTranslator()
    stamped = {"event": {"type": "ToolInvoked", "payload": {"toolCalling": {"id": "tc1"}}, "result": {"content": "ok"}, "isSuccess": True, "executionTime": 120}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "tool_end"
    assert "projected_state" not in out["data"]  # spec §5.3.1
    assert out["data"]["isSuccess"] is True
    assert out["data"]["result"] == {"content": "ok"}


def test_step_start_with_human_approval_has_requires_approval():
    t = EventTranslator()
    stamped = {"event": {"type": "StepStart", "phase": "human_approval", "requiresApproval": True, "pendingToolsCalling": [{"id": "tc1"}]}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "step_start"
    assert out["data"]["phase"] == "human_approval"
    assert out["data"]["requiresApproval"] is True
    assert out["data"]["pendingToolsCalling"] == [{"id": "tc1"}]


def test_spine_close_with_waiting_human_becomes_agent_runtime_end():
    t = EventTranslator()
    stamped = {"event": {"type": "SpineClose", "reason": "waiting_for_human", "final_state": {"status": "waiting_for_human"}}}
    out = t.translate(stamped)
    assert out is not None
    assert out["type"] == "agent_runtime_end"
    assert out["data"]["reason"] == "waiting_for_human"
    assert out["data"]["finalState"]["status"] == "waiting_for_human"
    assert out["data"]["phase"] == "execution_complete"


def test_spine_close_with_done_becomes_agent_runtime_end_completed():
    t = EventTranslator()
    stamped = {"event": {"type": "SpineClose", "reason": "completed", "final_state": {"status": "done"}}}
    out = t.translate(stamped)
    assert out["type"] == "agent_runtime_end"
    assert out["data"]["reason"] == "completed"


def test_unknown_event_returns_none():
    t = EventTranslator()
    assert t.translate({"event": {"type": "UnknownThing"}}) is None


def test_unknown_event_kind_returns_none():
    t = EventTranslator()
    assert t.translate({"event": {"type": "LlmCallTextDelta", "kind": "ignore"}}) is None
