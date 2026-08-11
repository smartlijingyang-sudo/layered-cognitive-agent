"""DiffProjector reasoning_section events — multi-step journal replay.

Drives a synthetic multi-step journal (≥3 steps with reasoning deltas +
tool calls) through the DiffProjector and asserts:
(a) at least N reasoning_section LCA events emitted
(b) each event's content field is non-empty and matches accumulated reasoning
(c) events carry the correct step field
"""

from __future__ import annotations

import json

import pytest

from gateway.projection.diff_projector import DiffProjector
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    LlmCallCompleted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    RunScope,
    StampedEvent,
    StepCompleted,
    StepTextDelta,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.observability.journal.journal_io import stamped_to_record

_SCOPE = RunScope(trace_id="t", run_id="r", agent_role="助手")
_BASE_TS = 1_000_000.0


def _record(seq: int, ts: float, event: object) -> str:
    """Build an SSE frame string from a journal event."""
    stamped = StampedEvent(seq=seq, ts=ts, scope=_SCOPE, event=event)  # type: ignore[arg-type]
    rec = stamped_to_record(stamped)
    return f"data: {json.dumps(rec)}\n"


def _build_multistep_journal() -> list[str]:
    """3-step journal: reasoning → tool → reasoning → tool → reasoning → answer."""
    frames: list[str] = []
    seq = 0
    ts = _BASE_TS

    def emit(event: object) -> None:
        nonlocal seq, ts
        seq += 1
        ts += 0.1
        frames.append(_record(seq, ts, event))

    # Run starts
    emit(AgentRunStarted(agent_role="助手", strategy_key="solo", objective="test"))

    # --- Step 0: reasoning → tool ---
    emit(LlmCallStarted(model="test-model", step=0))
    for text in ["Think step 0 part 1. ", "Think step 0 part 2. ", "Think step 0 part 3."]:
        emit(ReasoningDelta(step=0, text_delta=text, seq=seq))
    emit(
        ReasoningCompleted(
            step=0, content_preview="Think step 0 part 1. Think step 0 part 2. Think step 0 part 3."
        )
    )
    emit(LlmCallCompleted(model="test-model", prompt_tokens=100, completion_tokens=50))
    emit(
        ToolStarted(
            tool_name="execute_code", arguments_preview='{"code":"print(1)"}', invocation_id="inv_0"
        )
    )
    emit(ToolInvoked(tool_name="execute_code", ok=True, result_preview="1", invocation_id="inv_0"))
    emit(StepCompleted(step=0, action_type="use_tool"))

    # --- Step 1: reasoning → tool ---
    emit(LlmCallStarted(model="test-model", step=1))
    for text in ["Step 1 reasoning A. ", "Step 1 reasoning B."]:
        emit(ReasoningDelta(step=1, text_delta=text, seq=seq))
    emit(ReasoningCompleted(step=1, content_preview="Step 1 reasoning A. Step 1 reasoning B."))
    emit(LlmCallCompleted(model="test-model", prompt_tokens=200, completion_tokens=80))
    emit(
        ToolStarted(
            tool_name="execute_code", arguments_preview='{"code":"print(2)"}', invocation_id="inv_1"
        )
    )
    emit(ToolInvoked(tool_name="execute_code", ok=True, result_preview="2", invocation_id="inv_1"))
    emit(StepCompleted(step=1, action_type="use_tool"))

    # --- Step 2: reasoning → answer (no tool) ---
    emit(LlmCallStarted(model="test-model", step=2))
    for text in ["Final reasoning X. ", "Final reasoning Y. ", "Final reasoning Z."]:
        emit(ReasoningDelta(step=2, text_delta=text, seq=seq))
    emit(
        ReasoningCompleted(
            step=2, content_preview="Final reasoning X. Final reasoning Y. Final reasoning Z."
        )
    )
    emit(LlmCallCompleted(model="test-model", prompt_tokens=300, completion_tokens=120))
    emit(StepTextDelta(step=2, text_delta="The answer is 42.", channel="answer"))
    emit(StepCompleted(step=2, action_type="respond"))

    # Run finishes
    emit(AgentRunFinished(status="completed", output_text="done"))

    return frames


def _extract_lca_events(frames: list[str]) -> list[dict]:
    """Run frames through DiffProjector, collect all lca.events."""
    projector = DiffProjector(chat_id="test", model="test-model")
    events: list[dict] = []
    for frame in frames:
        for chunk in projector.project_frame(frame):
            lca = chunk.get("lca", {})
            if lca:
                events.extend(lca.get("events", []))
    return events


class TestDiffProjectorReasoningSections:
    """reasoning_section events from DiffProjector."""

    def test_emits_at_least_three_sections(self) -> None:
        frames = _build_multistep_journal()
        events = _extract_lca_events(frames)
        sections = [e for e in events if e.get("type") == "reasoning_section"]
        assert len(sections) >= 3, f"Expected ≥3 reasoning_section events, got {len(sections)}"

    def test_each_section_has_nonempty_content(self) -> None:
        frames = _build_multistep_journal()
        events = _extract_lca_events(frames)
        sections = [e for e in events if e.get("type") == "reasoning_section"]
        for s in sections:
            assert s.get("content"), f"reasoning_section step={s.get('step')} has empty content"

    def test_sections_have_correct_step_field(self) -> None:
        frames = _build_multistep_journal()
        events = _extract_lca_events(frames)
        sections = [e for e in events if e.get("type") == "reasoning_section"]
        steps = [s["step"] for s in sections]
        assert steps == [0, 1, 2], f"Expected steps [0, 1, 2], got {steps}"

    def test_section_content_matches_reasoning_text(self) -> None:
        frames = _build_multistep_journal()
        events = _extract_lca_events(frames)
        sections = [e for e in events if e.get("type") == "reasoning_section"]
        # Step 0 should contain all three reasoning parts
        assert "Think step 0 part 1." in sections[0]["content"]
        assert "Think step 0 part 3." in sections[0]["content"]
        # Step 1 should contain its reasoning
        assert "Step 1 reasoning A." in sections[1]["content"]
        # Step 2 should contain final reasoning
        assert "Final reasoning Z." in sections[2]["content"]

    def test_no_duplicate_sections(self) -> None:
        """Each step should produce exactly one reasoning_section event."""
        frames = _build_multistep_journal()
        events = _extract_lca_events(frames)
        sections = [e for e in events if e.get("type") == "reasoning_section"]
        steps = [s["step"] for s in sections]
        assert len(steps) == len(set(steps)), f"Duplicate steps in sections: {steps}"


class TestRealTraceReplay:
    """Replay a real journal trace and verify reasoning_section events."""

    def test_real_trace_produces_sections(self) -> None:
        import pathlib

        trace_path = (
            pathlib.Path(__file__).parent.parent / "traces" / "runs" / "run_0a0cd892b83b.jsonl"
        )
        if not trace_path.exists():
            pytest.skip("Real trace file not available")

        with open(trace_path) as f:
            raw_frames = f.readlines()

        projector = DiffProjector(chat_id="test", model="qwen3.7-plus")
        sections: list[dict] = []
        for raw in raw_frames:
            sse_frame = f"data: {raw.strip()}\n"
            for chunk in projector.project_frame(sse_frame):
                lca = chunk.get("lca", {})
                if lca:
                    for ev in lca.get("events", []):
                        if ev.get("type") == "reasoning_section":
                            sections.append(ev)

        assert len(sections) >= 5, f"Expected ≥5 sections from real trace, got {len(sections)}"
        for s in sections:
            assert s.get("content"), f"Empty content in step={s.get('step')}"
            assert isinstance(s.get("step"), int), "Missing step field"
