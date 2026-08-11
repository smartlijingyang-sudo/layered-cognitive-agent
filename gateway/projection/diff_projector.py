"""DiffProjector — pure-function turn-based projection to OpenAI SSE chunks.

Replaces the monolithic JournalOpenAiProjector with a clean architecture:

    Journal events
        → TurnStateMachine  (evolves TurnSnapshot, pure value)
        → DiffProjector     (diffs snapshots, emits SSE chunks)
        → ToolProjection    (delegates tool lifecycle events)

Key design principles:
    - TurnSnapshot is the single source of truth for reasoning/text state
    - DiffProjector tracks what has been emitted (cursor) and diffs
    - Tool lifecycle delegated to ToolProjection (existing, well-tested)
    - Reasoning blocks are properly bounded per turn (fixes "one big block")
    - stepCount comes from TurnSnapshot (fixes "steps=1")
    - Run finish forces lifecycle close (fixes "timer never stops")

This is the *mechanism* that aligns with LobeHub's native behavior:
    thinking block → tool card → thinking block → tool card → ... → answer
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

from gateway._tool_projection import ToolProjection
from gateway.lobehub_bridge.lca_sse_extension import (
    lca_reasoning_section_event,
    merge_lca_extension,
)
from gateway.presentation.turn_snapshot import (
    PhaseKind,
    Turn,
    TurnSnapshot,
)
from gateway.presentation.turn_state_machine import TurnStateMachine
from lca.contracts.models.observability.journal import (
    LlmCallCompleted,
    SandboxOutputDelta,
    StampedEvent,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

# ── Types ───────────────────────────────────────────────────

Chunk = dict[str, Any]
USER_FACING_TERMINAL_ACTIONS = frozenset({"respond", "stop", "ask_human"})
_ALLOWED_FINISH_REASONS = frozenset({None, "stop"})


# ── Cursor: tracks what has been emitted ────────────────────


@dataclass
class _EmitCursor:
    """Tracks what has been emitted to avoid duplicates."""

    reasoning_emitted: dict[int, int] = field(default_factory=dict)
    """turn_index → number of chars of reasoning_text already emitted."""

    answer_emitted: dict[int, int] = field(default_factory=dict)
    """turn_index → number of chars of answer_text already emitted."""

    reasoning_section_emitted: dict[int, bool] = field(default_factory=dict)
    """turn_index → whether a reasoning_section LCA event was emitted."""

    reasoning_block_open: bool = False
    """Whether a reasoning block is currently open in the SSE stream."""

    steps_emitted: bool = False
    """Whether stepCount has been emitted."""

    finish_emitted: bool = False
    """Whether the final stop chunk has been emitted."""

    role_emitted: bool = False
    """Whether the initial role chunk has been emitted."""


# ── DiffProjector ───────────────────────────────────────────


@dataclass
class DiffProjector:
    """Turn-based projector: journal events → OpenAI SSE chunks.

    Uses TurnStateMachine to build a structured representation,
    then diffs consecutive snapshots to emit minimal SSE changes.

    Tool lifecycle events are delegated to ToolProjection.
    """

    chat_id: str
    model: str

    # State machine — evolves the presentation
    _machine: TurnStateMachine = field(default_factory=TurnStateMachine)
    _snapshot: TurnSnapshot = field(default_factory=TurnSnapshot)

    # Cursor — tracks what has been emitted
    _cursor: _EmitCursor = field(default_factory=_EmitCursor)

    # Tool projection — delegated
    _tools: ToolProjection = field(init=False)

    # Token tracking
    _prompt_tokens: int = 0
    _completion_tokens: int = 0

    def __post_init__(self) -> None:
        self._tools = ToolProjection(
            emit_lca=self._wrap_lca_events,
            emit_delta=self._wrap_delta,
        )

    # ── Public API ──────────────────────────────────────────

    def project_frame(self, frame: str) -> list[dict[str, Any]]:
        """Process one journal SSE frame → list of OpenAI SSE chunks."""
        record = _parse_sse_frame(frame)
        if record is None:
            return []
        stamped = record_to_stamped(record)
        if stamped is None:
            return []

        # Track tokens from LlmCallCompleted
        if isinstance(stamped.event, LlmCallCompleted):
            self._prompt_tokens += int(stamped.event.prompt_tokens or 0)
            self._completion_tokens += int(stamped.event.completion_tokens or 0)

        # Delegate tool events to ToolProjection
        chunks = self._delegate_tool_events(stamped)
        if chunks is not None:
            return chunks

        # Evolve the turn snapshot
        old_snapshot = self._snapshot
        self._snapshot = self._machine.build(self._snapshot, stamped)

        # Diff snapshots → emit SSE chunks
        return self._diff(old_snapshot, self._snapshot)

    # ── Snapshot diffing ────────────────────────────────────

    def _diff(self, old: TurnSnapshot, new: TurnSnapshot) -> list[Chunk]:
        """Compute SSE chunks from the diff between two snapshots."""
        chunks: list[Chunk] = []

        # New turns added
        for i in range(len(old.turns), len(new.turns)):
            turn = new.turns[i]
            chunks.extend(self._emit_turn_start(turn, i))

        # Current turn updated
        if new.turns:
            curr_idx = new.current_turn_index
            if 0 <= curr_idx < len(new.turns):
                curr = new.turns[curr_idx]
                old_curr = old.turns[curr_idx] if curr_idx < len(old.turns) else None
                chunks.extend(self._diff_turn(curr, old_curr, curr_idx))

        # Run finished
        if new.finished and not old.finished:
            chunks.extend(self._emit_run_finished(new))

        return chunks

    def _emit_turn_start(self, turn: Turn, index: int) -> list[Chunk]:
        """Emit chunks when a new turn begins."""
        # Close any open reasoning block before starting a new turn
        chunks: list[Chunk] = []
        if self._cursor.reasoning_block_open:
            chunks.extend(self._close_reasoning_block())
        return chunks

    def _diff_turn(self, turn: Turn, old_turn: Turn | None, index: int) -> list[Chunk]:
        """Emit chunks for changes within a turn."""
        chunks: list[Chunk] = []

        # Reasoning text delta
        old_reasoning_len = self._cursor.reasoning_emitted.get(index, 0)
        new_reasoning_len = len(turn.reasoning_text)
        if new_reasoning_len > old_reasoning_len:
            # Open reasoning block if not already open
            if not self._cursor.reasoning_block_open:
                chunks.extend(self._open_reasoning_block())
            delta = turn.reasoning_text[old_reasoning_len:]
            chunks.extend(self._emit_delta({"reasoning_content": delta}))
            self._cursor.reasoning_emitted[index] = new_reasoning_len

        # Close reasoning block when phase transitions away from REASONING
        if (
            self._cursor.reasoning_block_open
            and turn.phase != PhaseKind.REASONING
            and turn.reasoning_text
            and (old_turn is None or old_turn.phase == PhaseKind.REASONING)
            and turn.phase in {PhaseKind.TOOL_CALL, PhaseKind.ANSWER}
        ):
            chunks.extend(self._close_reasoning_block())

        # Answer text delta
        old_answer_len = self._cursor.answer_emitted.get(index, 0)
        new_answer_len = len(turn.answer_text)
        if new_answer_len > old_answer_len:
            # Close reasoning block before emitting answer
            if self._cursor.reasoning_block_open:
                chunks.extend(self._close_reasoning_block())
            delta = turn.answer_text[old_answer_len:]
            chunks.extend(self._emit_delta({"content": delta}))
            self._cursor.answer_emitted[index] = new_answer_len

        return chunks

    # ── Run lifecycle ───────────────────────────────────────

    def _emit_run_finished(self, snapshot: TurnSnapshot) -> list[Chunk]:
        """Emit final chunks when the run completes."""
        chunks: list[Chunk] = []

        # Close any open reasoning block
        if self._cursor.reasoning_block_open:
            chunks.extend(self._close_reasoning_block())

        # Emit final output if nothing was emitted yet
        if snapshot.final_output and not any(self._cursor.answer_emitted.values()):
            chunks.extend(self._emit_delta({"content": snapshot.final_output}))

        # Emit finish chunk with usage
        if not self._cursor.finish_emitted:
            self._cursor.finish_emitted = True
            chunks.extend(self._emit_finish(snapshot))

        return chunks

    # ── Reasoning block management ──────────────────────────

    def _open_reasoning_block(self) -> list[Chunk]:
        """Open a new reasoning block (LobeHub sees start of thinking)."""
        if self._cursor.reasoning_block_open:
            return []
        self._cursor.reasoning_block_open = True
        # In LobeHub's StreamingHandler, reasoning starts automatically
        # when the first reasoning_content delta arrives. No explicit marker needed.
        return []

    def _close_reasoning_block(self) -> list[Chunk]:
        """Close the current reasoning block and emit a reasoning_section event.

        The reasoning_section event carries the complete thinking text for
        the current turn, so the frontend can save it as a finished
        "已深度思考" block and reset for the next step — producing separate
        collapsible sections per LLM call.
        """
        if not self._cursor.reasoning_block_open:
            return []
        self._cursor.reasoning_block_open = False

        # Emit reasoning_section with the current turn's full reasoning text
        chunks: list[Chunk] = []
        curr_idx = self._snapshot.current_turn_index
        if 0 <= curr_idx < len(
            self._snapshot.turns
        ) and not self._cursor.reasoning_section_emitted.get(curr_idx, False):
            turn = self._snapshot.turns[curr_idx]
            content = turn.reasoning_text
            if content:
                self._cursor.reasoning_section_emitted[curr_idx] = True
                section_event = lca_reasoning_section_event(
                    step=turn.step,
                    content=content,
                )
                chunks.extend(self._wrap_lca_events([section_event]))
        return chunks

    # ── Tool event delegation ───────────────────────────────

    def _delegate_tool_events(self, stamped: StampedEvent) -> list[Chunk] | None:
        """Delegate tool lifecycle events to ToolProjection.

        Returns None if the event is not a tool event (caller handles it).
        """
        event = stamped.event
        if isinstance(event, ToolStarted):
            # Close reasoning block before tool card — capture the
            # reasoning_section event so it's not lost.
            pre_chunks: list[Chunk] = []
            if self._cursor.reasoning_block_open:
                pre_chunks.extend(self._close_reasoning_block())
            return pre_chunks + self._tools.project_started(event)
        if isinstance(event, SandboxOutputDelta):
            return self._tools.project_sandbox_output(event)
        if isinstance(event, ToolInvoked):
            return self._tools.project_invoked(event)
        if isinstance(event, ToolDenied):
            return self._tools.project_denied(event)
        return None

    # ── Chunk formatting ────────────────────────────────────

    def _emit_delta(self, delta: dict[str, Any]) -> list[Chunk]:
        """Emit a content/reasoning delta chunk."""
        if not self._cursor.role_emitted:
            self._cursor.role_emitted = True
            return [self._chunk({"role": "assistant", **delta})]
        return [self._chunk(delta)]

    def _wrap_delta(self, parts: list[dict[str, Any]]) -> list[Chunk]:
        """Adapt ToolProjection's list-of-deltas callback."""
        chunks: list[Chunk] = []
        for part in parts:
            chunks.extend(self._emit_delta(part))
        return chunks

    def _wrap_lca_events(self, events: list[dict[str, Any]]) -> list[Chunk]:
        """Wrap LCA extension events into a chunk."""
        if not events:
            return []
        return [merge_lca_extension(self._chunk({}), events)]

    def _emit_finish(self, snapshot: TurnSnapshot) -> list[Chunk]:
        """Emit the final stop chunk with usage metadata."""
        usage: dict[str, int] | None = None
        if self._prompt_tokens or self._completion_tokens:
            usage = {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
            }
        return [self._chunk({}, finish_reason="stop", usage=usage)]

    def _chunk(
        self,
        delta: dict[str, Any],
        *,
        finish_reason: str | None = None,
        usage: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Build an OpenAI chat.completion.chunk."""
        body: dict[str, Any] = {
            "id": self.chat_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        if usage is not None:
            body["usage"] = usage
        return body

    def completion_json(self, content: str, *, finish_reason: str = "stop") -> dict[str, Any]:
        """Non-streaming chat.completion response."""
        return {
            "id": self.chat_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
            },
        }


# ── Module-level utilities ──────────────────────────────────


def _parse_sse_frame(frame: str) -> dict[str, Any] | None:
    """Extract JSON record from a journal SSE frame."""
    for line in frame.splitlines():
        if line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


def assert_openai_finish_invariant(chunks: list[dict[str, Any]]) -> None:
    """Mode A contract: outward SSE must never signal tool-loop continuation."""
    stop_count = 0
    for chunk in chunks:
        choice = chunk.get("choices", [{}])[0]
        reason = choice.get("finish_reason")
        if reason not in _ALLOWED_FINISH_REASONS:
            raise ValueError(f"invalid outward finish_reason: {reason!r}")
        delta = choice.get("delta") or {}
        if delta.get("tool_calls"):
            raise ValueError("Mode A closed-loop must not emit delta.tool_calls")
        if reason == "stop":
            stop_count += 1
    if chunks and stop_count != 1:
        raise ValueError(f"expected exactly one stop chunk, got {stop_count}")


def sse_data_lines(chunks: Iterator[dict[str, Any]]) -> Iterator[bytes]:
    for chunk in chunks:
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode()
    yield b"data: [DONE]\n\n"


async def stream_openai_from_run(
    frame_stream: AsyncIterator[str],
    *,
    chat_id: str,
    model: str,
) -> AsyncIterator[bytes]:
    """Stream standard OpenAI SSE chunks for LobeHub model-runtime.

    Uses DiffProjector (turn-based) instead of the old JournalOpenAiProjector.
    """
    projector = DiffProjector(chat_id=chat_id, model=model)
    async for frame in frame_stream:
        for chunk in projector.project_frame(frame):
            yield b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"
    if not projector._cursor.finish_emitted:
        for chunk in projector._emit_finish(projector._snapshot):
            yield b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"
    yield b"data: [DONE]\n\n"


async def collect_openai_completion(
    frame_stream: AsyncIterator[str],
    *,
    chat_id: str,
    model: str,
) -> dict[str, Any]:
    """Non-streaming: collect all content into a single completion response."""
    projector = DiffProjector(chat_id=chat_id, model=model)
    parts: list[str] = []
    async for frame in frame_stream:
        for chunk in projector.project_frame(frame):
            delta = chunk["choices"][0].get("delta") or {}
            text = delta.get("content")
            if isinstance(text, str) and text:
                parts.append(text)
    return projector.completion_json("".join(parts))
