"""Golden trace replay — validates new projector against real journal data.

Replays traces/runs/run_148968ffc177.jsonl (PDF generation, 10 steps,
2 failed execute_code calls) through the new OpenAISSEProjector and verifies
the SSE output matches expected LobeHub-native behavior:

    - Multiple reasoning blocks (not one big blob)
    - Tool cards for all 9 invocations
    - stepCount = 10 (from AgentRunFinished)
    - No </think> leak in content
    - Timer close on run finish
    - Artifacts with absolute URLs
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway.narrative.turn_builder import TurnBuilder
from gateway.projection.openai_sse import OpenAISSEProjector
from lca.contracts.models.observability.journal import StampedEvent
from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

GOLDEN_TRACE = Path("traces/runs/run_148968ffc177.jsonl")


@pytest.fixture
def golden_events() -> list[StampedEvent]:
    """Load the PDF generation golden trace."""
    if not GOLDEN_TRACE.exists():
        pytest.skip(f"Golden trace not found: {GOLDEN_TRACE}")
    events: list[StampedEvent] = []
    for line in GOLDEN_TRACE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        stamped = record_to_stamped(record)
        if stamped is not None:
            events.append(stamped)
    return events


class TestGoldenTraceStateMachine:
    """Verify TurnBuilder builds correct structure from real data."""

    def test_creates_multiple_turns(self, golden_events: list[StampedEvent]) -> None:
        """The PDF run has 10 steps — should produce multiple turns."""
        machine = TurnBuilder()
        snapshot = machine.build_all(golden_events)
        # Should have multiple turns (not just 1)
        assert len(snapshot.turns) > 1, (
            f"Expected multiple turns, got {len(snapshot.turns)}. "
            f"Reasoning is collapsed into one block."
        )

    def test_steps_total_is_10(self, golden_events: list[StampedEvent]) -> None:
        """AgentRunFinished.steps=10 must be reflected."""
        machine = TurnBuilder()
        snapshot = machine.build_all(golden_events)
        assert snapshot.finished is True
        assert snapshot.steps_total == 10, (
            f"Expected steps_total=10, got {snapshot.steps_total}. "
            f"UI will show '共运行 {snapshot.steps_total} 步'."
        )

    def test_all_tools_reach_terminal(self, golden_events: list[StampedEvent]) -> None:
        """close_all at run finish should close all open tools."""
        machine = TurnBuilder()
        snapshot = machine.build_all(golden_events)
        assert snapshot.finished is True
        # After run finish, no tool should be open
        assert machine.lifecycle.open_count == 0, (
            f"{machine.lifecycle.open_count} tools still open after run finish. "
            f"Timer will never stop."
        )

    def test_artifacts_collected(self, golden_events: list[StampedEvent]) -> None:
        """The successful execute_code produces a PDF file artifact."""
        machine = TurnBuilder()
        machine.build_all(golden_events)
        # Use the ArtifactRegistry
        artifacts = machine.artifacts.list_all()
        assert len(artifacts) >= 1, "Expected at least 1 artifact (the PDF)"
        pdf_artifacts = [a for a in artifacts if "pdf" in a.name.lower()]
        assert len(pdf_artifacts) >= 1
        assert pdf_artifacts[0].mime_type == "application/pdf"
        # URL should be absolute (resolved by ArtifactRegistry)
        assert pdf_artifacts[0].url.startswith("http"), (
            f"Artifact URL should be absolute, got: {pdf_artifacts[0].url}"
        )

    def test_has_reasoning_and_answer_turns(self, golden_events: list[StampedEvent]) -> None:
        """Should have turns with reasoning text AND turns with answer text."""
        machine = TurnBuilder()
        snapshot = machine.build_all(golden_events)
        reasoning_turns = [t for t in snapshot.turns if t.reasoning_text]
        answer_turns = [t for t in snapshot.turns if t.answer_text]
        assert len(reasoning_turns) >= 1, "No reasoning turns found"
        assert len(answer_turns) >= 1, "No answer turns found"


class TestGoldenTraceProjector:
    """Verify OpenAISSEProjector produces correct SSE from real data."""

    def _replay(self, golden_events: list[StampedEvent]) -> list[dict]:
        """Replay events through OpenAISSEProjector, collect all chunks."""
        import dataclasses

        proj = OpenAISSEProjector(chat_id="chat_test", model="qwen3.7-plus")
        all_chunks: list[dict] = []
        for stamped in golden_events:
            record = {
                "schema": "journal.v1",
                "seq": stamped.seq,
                "ts": stamped.ts,
                "scope": dataclasses.asdict(stamped.scope),
                "event_type": type(stamped.event).__name__,
                "event": dataclasses.asdict(stamped.event),
            }
            frame = f"data: {json.dumps(record)}\n\n"
            chunks = proj.project_frame(frame)
            all_chunks.extend(chunks)
        return all_chunks

    def test_has_stop_chunk(self, golden_events: list[StampedEvent]) -> None:
        chunks = self._replay(golden_events)
        stop_chunks = [
            c for c in chunks if c.get("choices", [{}])[0].get("finish_reason") == "stop"
        ]
        assert len(stop_chunks) >= 1, "No stop chunk emitted"

    def test_has_reasoning_content(self, golden_events: list[StampedEvent]) -> None:
        chunks = self._replay(golden_events)
        reasoning = [
            c["choices"][0]["delta"]["reasoning_content"]
            for c in chunks
            if c.get("choices", [{}])[0].get("delta", {}).get("reasoning_content")
        ]
        full_reasoning = "".join(reasoning)
        assert len(full_reasoning) > 100, (
            f"Expected substantial reasoning text, got {len(full_reasoning)} chars"
        )

    def test_no_think_tag_in_content(self, golden_events: list[StampedEvent]) -> None:
        """No </think> should appear in content (answer) channel."""
        chunks = self._replay(golden_events)
        content_texts = [
            c["choices"][0]["delta"]["content"]
            for c in chunks
            if c.get("choices", [{}])[0].get("delta", {}).get("content")
        ]
        full_content = "".join(content_texts)
        think_close_tag = "</think>"
        assert think_close_tag not in full_content, (
            f"think tag leaked into content channel. Content: {full_content[:200]!r}"
        )

    def test_has_tool_events(self, golden_events: list[StampedEvent]) -> None:
        """Should emit lca.events for tool lifecycle."""
        chunks = self._replay(golden_events)
        lca_chunks = [c for c in chunks if c.get("lca")]
        assert len(lca_chunks) >= 9, (
            f"Expected ≥9 tool event chunks (9 tool invocations), got {len(lca_chunks)}"
        )

    def test_has_answer_content(self, golden_events: list[StampedEvent]) -> None:
        """The final answer should contain the PDF reference."""
        chunks = self._replay(golden_events)
        content_texts = [
            c["choices"][0]["delta"]["content"]
            for c in chunks
            if c.get("choices", [{}])[0].get("delta", {}).get("content")
        ]
        full_content = "".join(content_texts)
        assert "pdf" in full_content.lower() or "任务已完成" in full_content, (
            f"Expected final answer with PDF reference. Got: {full_content[:200]!r}"
        )
