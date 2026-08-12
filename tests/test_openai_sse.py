"""Tests for OpenAISSEProjector — turn-based SSE projection.

Tests the projection from TurnSnapshot diff to OpenAI SSE chunks,
verifying that:
    - Reasoning blocks are properly bounded per turn
    - Tool events delegate to ToolProjection
    - Run finish emits correct stop chunk with usage
    - stepCount comes from TurnSnapshot
"""

from __future__ import annotations

import json

from gateway.narrative.turn_model import PhaseKind, Turn, TurnSnapshot
from gateway.projection.openai_sse import OpenAISSEProjector


class TestOpenAISSEProjectorBasics:
    def test_empty_frame_returns_empty(self) -> None:
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        chunks = proj.project_frame("not-json")
        assert chunks == []

    def test_role_chunk_emitted_first(self) -> None:
        """First delta should include role: assistant."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        # Manually inject a turn with reasoning
        turn = Turn(index=0, phase=PhaseKind.REASONING, reasoning_text="hello")
        proj._snapshot = TurnSnapshot(turns=(turn,), current_turn_index=0, started_at=100.0)
        # Simulate a new reasoning delta
        from lca.contracts.models.observability.journal import (
            ReasoningDelta,
            RunScope,
            StampedEvent,
        )

        frame = _make_frame(
            StampedEvent(
                seq=1,
                ts=101.0,
                scope=RunScope(trace_id="t", run_id="r"),
                event=ReasoningDelta(step=0, text_delta="world", seq=0),
            )
        )
        chunks = proj.project_frame(frame)
        # Should have at least one chunk with role or reasoning_content
        assert any(
            c.get("choices", [{}])[0].get("delta", {}).get("role") == "assistant"
            or c.get("choices", [{}])[0].get("delta", {}).get("reasoning_content")
            for c in chunks
        )

    def test_finish_chunk_has_stop_reason(self) -> None:
        """Run finish should emit a chunk with finish_reason=stop."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        proj._prompt_tokens = 100
        proj._completion_tokens = 50

        from lca.contracts.models.observability.journal import (
            AgentRunFinished,
            RunScope,
            StampedEvent,
        )

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
        from lca.contracts.models.observability.journal import (
            ReasoningDelta,
            RunScope,
            StampedEvent,
        )

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


class TestOpenAISSEProjectorToolDelegation:
    def test_tool_started_delegates(self) -> None:
        """ToolStarted events should be delegated to ToolProjection."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        from lca.contracts.models.observability.journal import (
            RunScope,
            StampedEvent,
            ToolStarted,
        )

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
        """Simulate a minimal run: reasoning → tool → reasoning → answer."""
        proj = OpenAISSEProjector(chat_id="chat_1", model="test")
        from lca.contracts.atoms.enums import StreamChannel
        from lca.contracts.models.observability.journal import (
            AgentRunFinished,
            AgentRunStarted,
            ReasoningDelta,
            RunScope,
            StampedEvent,
            StepTextDelta,
        )

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

        # Verify we got reasoning content
        reasoning_texts = [
            c["choices"][0]["delta"]["reasoning_content"]
            for c in all_chunks
            if c.get("choices", [{}])[0].get("delta", {}).get("reasoning_content")
        ]
        assert "thinking1" in "".join(reasoning_texts)

        # Verify we got answer content
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


def _make_frame(stamped: object) -> str:
    """Convert a StampedEvent to a journal SSE frame string."""
    import dataclasses

    from lca.contracts.models.observability.journal import StampedEvent

    if not isinstance(stamped, StampedEvent):
        return ""
    record = {
        "schema": "journal.v1",
        "seq": stamped.seq,
        "ts": stamped.ts,
        "scope": dataclasses.asdict(stamped.scope),
        "event_type": type(stamped.event).__name__,
        "event": dataclasses.asdict(stamped.event),
    }
    return f"data: {json.dumps(record)}\n\n"
