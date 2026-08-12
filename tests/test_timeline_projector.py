"""TimelineProjector whitelist — sole UI wire contract tests."""

from __future__ import annotations

from gateway.timeline import EVENT_TYPES, TimelineProjector, project_all
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    ReasoningCompleted,
    ReasoningDelta,
    RunScope,
    SandboxOutputDelta,
    StampedEvent,
    StepTextDelta,
    ToolCallStreaming,
    ToolInvoked,
    ToolStarted,
)


def _s(seq: int, event: object) -> StampedEvent:
    return StampedEvent(
        seq=seq,
        ts=1.0,
        scope=RunScope(trace_id="t", run_id="run_x"),
        event=event,
    )


def test_closed_event_set_and_order() -> None:
    events = project_all(
        [
            _s(1, AgentRunStarted(objective="hi")),
            _s(2, ReasoningDelta(step=0, text_delta="think", seq=0)),
            _s(3, ReasoningCompleted(step=0, duration_ms=10, content_preview="think")),
            _s(
                4,
                StepTextDelta(step=0, text_delta="ans", channel=StreamChannel.ANSWER.value),
            ),
            _s(5, DecisionMade(step=0, action_type="use_tool")),
            _s(6, ToolCallStreaming(tool_name="run_command", tool_call_id="c1")),
            _s(
                7,
                ToolStarted(
                    tool_name="list_files",
                    arguments_preview='{"directoryPath":"/mnt/data"}',
                    invocation_id="inv_a",
                ),
            ),
            _s(
                8,
                ToolInvoked(
                    tool_name="list_files",
                    arguments_preview="{}",
                    result_preview="ok",
                    ok=True,
                    invocation_id="inv_a",
                ),
            ),
            _s(9, AgentRunFinished(status="completed", output_text="done", steps=1)),
        ]
    )
    types = [e["type"] for e in events]
    assert all(t in EVENT_TYPES for t in types)
    assert types[0] == "run.start"
    assert types[-1] == "run.end"
    assert "thinking.delta" in types
    assert "thinking.end" in types
    assert "answer.delta" in types
    assert "tool.start" in types
    assert "tool.end" in types
    assert "tool_call_streaming" not in types
    assert "DecisionMade" not in types


def test_run_end_flushes_answer_before_terminal() -> None:
    out = project_all(
        [_s(1, AgentRunFinished(status="completed", output_text="final note", steps=0))]
    )
    assert out[0]["type"] == "answer.delta"
    assert "final note" in out[0]["text"]
    assert out[-1]["type"] == "run.end"


def test_decision_channel_dropped() -> None:
    out = project_all(
        [
            _s(
                1,
                StepTextDelta(step=0, text_delta="secret", channel=StreamChannel.DECISION.value),
            )
        ]
    )
    assert out == []


def test_tool_delta_keeps_code_from_args() -> None:
    p = TimelineProjector()
    p.project(
        _s(
            1,
            ToolStarted(
                tool_name="execute_code",
                arguments_preview='{"code":"print(1)","language":"python"}',
                invocation_id="inv-3",
            ),
        )
    )
    deltas = p.project(
        _s(
            2,
            SandboxOutputDelta(invocation_id="inv-3", stream="stdout", text_delta="1\n", seq=1),
        )
    )
    assert deltas
    assert deltas[0]["type"] == "tool.delta"
    assert deltas[0]["state"]["stdout"] == "1\n"
    assert deltas[0]["state"]["code"] == "print(1)"


def test_no_events_after_run_end() -> None:
    p = TimelineProjector()
    p.project(_s(1, AgentRunFinished(status="completed", steps=0)))
    late = p.project(_s(2, ReasoningDelta(step=1, text_delta="ghost", seq=0)))
    assert late == []
