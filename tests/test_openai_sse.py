"""Tests for OpenAISSEProjector — direct event-to-chunk projection.

Verifies:
    - Reasoning deltas → reasoning_content
    - Answer text → content
    - Tool events → delegated to ToolEventProjector
    - Run finish → stop chunk + usage + steps
    - Run error → lca.events run_error
"""

from __future__ import annotations

import dataclasses
import json

from gateway.projection.openai_sse import OpenAISSEProjector
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    ReasoningDelta,
    RunScope,
    StampedEvent,
    StepTextDelta,
    ToolStarted,
)


class TestOpenAISSEProjectorBasics:
    def test_empty_frame_returns_empty(self) -> None:
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        chunks = proj.project_frame("not-json")
        assert chunks == []

    def test_role_chunk_emitted_first(self) -> None:
        """First delta should include role: assistant."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        frame = _make_frame(
            StampedEvent(
                seq=1,
                ts=100.0,
                scope=RunScope(trace_id="t", run_id="r"),
                event=ReasoningDelta(step=0, text_delta="hello", seq=0),
            )
        )
        chunks = proj.project_frame(frame)
        # First chunk should have role: assistant
        assert chunks[0]["choices"][0]["delta"].get("role") == "assistant"
        assert chunks[0]["choices"][0]["delta"].get("reasoning_content") == "hello"

    def test_finish_chunk_has_stop_reason(self) -> None:
        """Run finish should emit a chunk with finish_reason=stop."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        proj._prompt_tokens = 100
        proj._completion_tokens = 50

        frame = _make_frame(
            StampedEvent(
                seq=10,
                ts=200.0,
                scope=RunScope(trace_id="t", run_id="r"),
                event=AgentRunFinished(status="completed", output_text="done", steps=5),
            )
        )
        chunks = proj.project_frame(frame)
        stop_chunks = [
            c for c in chunks if c.get("choices", [{}])[0].get("finish_reason") == "stop"
        ]
        assert len(stop_chunks) == 1
        usage = stop_chunks[0].get("usage", {})
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 50
        assert usage["total_tokens"] == 150

    def test_reasoning_content_emitted(self) -> None:
        """Reasoning deltas should produce reasoning_content in SSE."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        frame = _make_frame(
            StampedEvent(
                seq=1,
                ts=100.0,
                scope=RunScope(trace_id="t", run_id="r"),
                event=ReasoningDelta(step=0, text_delta="thinking...", seq=0),
            )
        )
        chunks = proj.project_frame(frame)
        reasoning_chunks = [
            c for c in chunks if c.get("choices", [{}])[0].get("delta", {}).get("reasoning_content")
        ]
        assert len(reasoning_chunks) >= 1
        assert "thinking..." in reasoning_chunks[0]["choices"][0]["delta"]["reasoning_content"]

    def test_steps_total_emitted_in_finish(self) -> None:
        """Steps total should be in run_meta lca event on finish chunk."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        frame = _make_frame(
            StampedEvent(
                seq=1,
                ts=100.0,
                scope=RunScope(trace_id="t", run_id="r"),
                event=AgentRunFinished(status="completed", output_text="", steps=3),
            )
        )
        chunks = proj.project_frame(frame)
        lca_chunks = [c for c in chunks if c.get("lca")]
        assert len(lca_chunks) >= 1
        events = lca_chunks[0]["lca"]["events"]
        run_meta = [e for e in events if e.get("type") == "run_meta"]
        assert len(run_meta) == 1
        assert run_meta[0]["steps"] == 3

    def test_run_error_emitted(self) -> None:
        """Failed run should emit run_error lca event."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        frame = _make_frame(
            StampedEvent(
                seq=1,
                ts=100.0,
                scope=RunScope(trace_id="t", run_id="r"),
                event=AgentRunFinished(status="failed", error="something broke", steps=0),
            )
        )
        chunks = proj.project_frame(frame)
        lca_chunks = [c for c in chunks if c.get("lca")]
        assert len(lca_chunks) >= 1
        events = lca_chunks[0]["lca"]["events"]
        errors = [e for e in events if e.get("type") == "run_error"]
        assert len(errors) == 1
        assert "something broke" in errors[0]["message"]


class TestOpenAISSEProjectorToolDelegation:
    def test_tool_started_delegates(self) -> None:
        """ToolStarted events should be delegated to ToolEventProjector."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        frame = _make_frame(
            StampedEvent(
                seq=1,
                ts=100.0,
                scope=RunScope(trace_id="t", run_id="r"),
                event=ToolStarted(
                    tool_name="execute_code",
                    arguments_preview='{"code": "print(1)"}',
                    invocation_id="inv_1",
                ),
            )
        )
        chunks = proj.project_frame(frame)
        # Should have an lca.events extension with tool_started
        lca_chunks = [c for c in chunks if c.get("lca")]
        assert len(lca_chunks) >= 1


class TestOpenAISSEProjectorIntegration:
    def test_full_run_scenario(self) -> None:
        """Simulate a minimal run: reasoning → answer → finish."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        scope = RunScope(trace_id="t", run_id="r")
        all_chunks: list[dict] = []

        events = [
            StampedEvent(seq=1, ts=100.0, scope=scope, event=AgentRunStarted(objective="test")),
            StampedEvent(
                seq=2,
                ts=101.0,
                scope=scope,
                event=ReasoningDelta(step=0, text_delta="thinking1", seq=0),
            ),
            StampedEvent(
                seq=3,
                ts=102.0,
                scope=scope,
                event=ReasoningDelta(step=0, text_delta=" more", seq=1),
            ),
            StampedEvent(
                seq=4,
                ts=103.0,
                scope=scope,
                event=StepTextDelta(
                    step=0,
                    text_delta="Here is the answer",
                    seq=2,
                    channel=StreamChannel.ANSWER.value,
                ),
            ),
            StampedEvent(
                seq=5,
                ts=104.0,
                scope=scope,
                event=AgentRunFinished(
                    status="completed", output_text="Here is the answer", steps=1
                ),
            ),
        ]

        for ev in events:
            frame = _make_frame(ev)
            chunks = proj.project_frame(frame)
            all_chunks.extend(chunks)

        # Verify reasoning content
        reasoning_texts = [
            c["choices"][0]["delta"]["reasoning_content"]
            for c in all_chunks
            if c.get("choices", [{}])[0].get("delta", {}).get("reasoning_content")
        ]
        assert "thinking1" in "".join(reasoning_texts)

        # Verify answer content
        answer_texts = [
            c["choices"][0]["delta"]["content"]
            for c in all_chunks
            if c.get("choices", [{}])[0].get("delta", {}).get("content")
        ]
        assert "Here is the answer" in "".join(answer_texts)

        # Verify finish chunk
        stop_chunks = [
            c for c in all_chunks if c.get("choices", [{}])[0].get("finish_reason") == "stop"
        ]
        assert len(stop_chunks) == 1


# ── Helpers ─────────────────────────────────────────────────


def _make_frame(stamped: StampedEvent) -> str:
    """Convert a StampedEvent to a journal SSE frame string."""
    record = {
        "schema": "journal.v1",
        "seq": stamped.seq,
        "ts": stamped.ts,
        "scope": dataclasses.asdict(stamped.scope),
        "event_type": type(stamped.event).__name__,
        "event": dataclasses.asdict(stamped.event),
    }
    return f"data: {json.dumps(record)}\n\n"
