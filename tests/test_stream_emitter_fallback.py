"""Tests for OpenAIStreamEmitter event forwarding — no silent drops."""

from __future__ import annotations

import pytest

from gateway.stream_emitter import OpenAIStreamEmitter
from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunStarted,
    CastingCompleted,
    CastingStarted,
    DecisionMade,
    DelegationCacheHit,
    ReasoningDelta,
    RunActivity,
    RunScope,
    StampedEvent,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    ToolStarted,
)


def _make_stamped(event, *, seq: int = 1) -> StampedEvent:
    scope = RunScope(
        trace_id="trace_test",
        run_id="run_test",
        parent_run_id=None,
        delegation_id=None,
        agent_role="助手",
    )
    return StampedEvent(seq=seq, ts=1000.0, scope=scope, event=event)


def _extract_lca_events(chunks: list[dict]) -> list[dict]:
    result = []
    for chunk in chunks:
        lca = chunk.get("lca")
        if lca and lca.get("events"):
            result.extend(lca["events"])
    return result


@pytest.fixture()
def emitter() -> OpenAIStreamEmitter:
    return OpenAIStreamEmitter(chat_id="chatcmpl-test", model="solo")


class TestEventForwardingFallback:
    """Previously dropped events must now be forwarded as lca.events."""

    def test_decision_made_forwarded(self, emitter: OpenAIStreamEmitter) -> None:
        event = DecisionMade(step=1, action_type="use_tool", tool_name="execute_code")
        chunks = emitter.consume(_make_stamped(event))
        events = _extract_lca_events(chunks)
        assert len(events) == 1
        assert events[0]["type"] == "DecisionMade"
        assert events[0]["action_type"] == "use_tool"
        assert events[0]["tool_name"] == "execute_code"

    def test_step_completed_forwarded(self, emitter: OpenAIStreamEmitter) -> None:
        event = StepCompleted(step=2, status="ok", action_type="respond")
        chunks = emitter.consume(_make_stamped(event))
        events = _extract_lca_events(chunks)
        assert len(events) == 1
        assert events[0]["type"] == "StepCompleted"
        assert events[0]["step"] == 2

    def test_run_activity_forwarded(self, emitter: OpenAIStreamEmitter) -> None:
        event = RunActivity(phase="tool_exec", step=1, detail="running")
        chunks = emitter.consume(_make_stamped(event))
        events = _extract_lca_events(chunks)
        assert len(events) == 1
        assert events[0]["type"] == "RunActivity"
        assert events[0]["phase"] == "tool_exec"

    def test_action_degraded_forwarded(self, emitter: OpenAIStreamEmitter) -> None:
        event = ActionDegraded(original_action_type="use_tool", degraded_to="respond", step=3)
        chunks = emitter.consume(_make_stamped(event))
        events = _extract_lca_events(chunks)
        assert len(events) == 1
        assert events[0]["type"] == "ActionDegraded"
        assert events[0]["degraded_to"] == "respond"

    def test_casting_events_forwarded(self, emitter: OpenAIStreamEmitter) -> None:
        started = CastingStarted(objective_preview="analyze data")
        completed = CastingCompleted(governance_kind="solo", lead_role="助手")
        for event in (started, completed):
            chunks = emitter.consume(_make_stamped(event))
            events = _extract_lca_events(chunks)
            assert len(events) == 1
            assert events[0]["type"] == type(event).__name__

    def test_delegation_cache_hit_forwarded(self, emitter: OpenAIStreamEmitter) -> None:
        event = DelegationCacheHit(step=1, callee_role="研究员", subtask_preview="cached")
        chunks = emitter.consume(_make_stamped(event))
        events = _extract_lca_events(chunks)
        assert len(events) == 1
        assert events[0]["type"] == "DelegationCacheHit"

    def test_synthesis_completed_forwarded(self, emitter: OpenAIStreamEmitter) -> None:
        event = SynthesisCompleted(method="consensus", candidate_count=3)
        chunks = emitter.consume(_make_stamped(event))
        events = _extract_lca_events(chunks)
        assert len(events) == 1
        assert events[0]["type"] == "SynthesisCompleted"

    def test_decision_channel_text_forwarded(self, emitter: OpenAIStreamEmitter) -> None:
        event = StepTextDelta(step=1, text_delta="thinking aloud", channel="decision")
        chunks = emitter.consume(_make_stamped(event))
        events = _extract_lca_events(chunks)
        assert len(events) == 1
        assert events[0]["type"] == "StepTextDelta"
        assert events[0]["channel"] == "decision"
        assert events[0]["text_delta"] == "thinking aloud"


class TestExistingBehaviorPreserved:
    """Previously handled events must still work as before."""

    def test_reasoning_delta_still_emits_delta(self, emitter: OpenAIStreamEmitter) -> None:
        event = ReasoningDelta(step=0, text_delta="let me think")
        chunks = emitter.consume(_make_stamped(event))
        assert len(chunks) == 1
        delta = chunks[0]["choices"][0]["delta"]
        assert delta.get("reasoning_content") == "let me think"
        assert _extract_lca_events(chunks) == []

    def test_answer_text_still_emits_content(self, emitter: OpenAIStreamEmitter) -> None:
        event = StepTextDelta(step=1, text_delta="hello world", channel="answer")
        chunks = emitter.consume(_make_stamped(event))
        assert len(chunks) == 1
        delta = chunks[0]["choices"][0]["delta"]
        assert delta.get("content") == "hello world"
        assert _extract_lca_events(chunks) == []

    def test_tool_started_still_emits_lca_event(self, emitter: OpenAIStreamEmitter) -> None:
        event = ToolStarted(
            tool_name="execute_code",
            invocation_id="inv_test",
            arguments_preview='{"code": "print(1)"}',
        )
        chunks = emitter.consume(_make_stamped(event))
        events = _extract_lca_events(chunks)
        assert any(e["type"] == "tool_started" for e in events)

    def test_run_started_still_emits_role_chunk(self, emitter: OpenAIStreamEmitter) -> None:
        event = AgentRunStarted(agent_role="助手", strategy_key="solo")
        chunks = emitter.consume(_make_stamped(event))
        assert len(chunks) == 1
        delta = chunks[0]["choices"][0]["delta"]
        assert delta.get("role") == "assistant"
