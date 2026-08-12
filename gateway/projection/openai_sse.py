"""OpenAISSEProjector — journal events → OpenAI SSE chunks.

Architecture::

    Journal events
        → TurnBuilder       (evolves TurnSnapshot, pure value)
        → OpenAISSEProjector (diffs snapshots, emits SSE chunks)
        → ToolEventProjector (delegates tool lifecycle events)

Design principles:
    - TurnSnapshot is the single source of truth for reasoning/text state
    - _EmitTracker tracks what has been emitted to avoid duplicates
    - Tool lifecycle delegated to ToolEventProjector
    - Reasoning content passes through as ``reasoning_content`` deltas —
      no block management, no section events, no buffering
    - Run errors surface as ``lca.events`` → ``run_error``
    - Steps total emitted in finish chunk via ``lca.events`` → ``run_meta``
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

from gateway.lobehub_bridge.lca_sse_extension import (
    lca_run_error_event,
    merge_lca_extension,
)
from gateway.narrative.turn_builder import TurnBuilder
from gateway.narrative.turn_model import Turn, TurnSnapshot
from gateway.projection.tool_events import ToolEventProjector
from lca.contracts.models.observability.journal import (
    DelegationCompleted,
    DelegationIssued,
    LlmCallCompleted,
    SandboxOutputDelta,
    StampedEvent,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

# ── Types ───────────────────────────────────────────────────

Chunk = dict[str, Any]
_ALLOWED_FINISH_REASONS = frozenset({None, "stop"})


# ── Tracker: what has been emitted ─────────────────────────


@dataclass
class _EmitTracker:
    """Tracks emitted content to avoid duplicates."""

    reasoning_emitted: dict[int, int] = field(default_factory=dict)
    """turn_index → chars of reasoning_text already emitted."""

    answer_emitted: dict[int, int] = field(default_factory=dict)
    """turn_index → chars of answer_text already emitted."""

    finish_emitted: bool = False
    role_emitted: bool = False


# ── OpenAISSEProjector ─────────────────────────────────────


@dataclass
class OpenAISSEProjector:
    """Journal events → OpenAI SSE chunks.

    Uses TurnBuilder to build structured representation,
    diffs consecutive snapshots, emits minimal SSE changes.
    """

    chat_id: str
    model: str

    _machine: TurnBuilder = field(default_factory=TurnBuilder)
    _snapshot: TurnSnapshot = field(default_factory=TurnSnapshot)
    _cursor: _EmitTracker = field(default_factory=_EmitTracker)
    _tools: ToolEventProjector = field(init=False)
    _prompt_tokens: int = 0
    _completion_tokens: int = 0

    def __post_init__(self) -> None:
        self._tools = ToolEventProjector(
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

        event = stamped.event

        # Token tracking
        if isinstance(event, LlmCallCompleted):
            self._prompt_tokens += int(event.prompt_tokens or 0)
            self._completion_tokens += int(event.completion_tokens or 0)

        # Delegation events — direct content emission (team mode)
        if isinstance(event, DelegationIssued):
            text = f"\n\n⇢ **委派** → `{event.callee_role}`: {event.subtask_preview}\n"
            return self._emit_delta({"content": text})
        if isinstance(event, DelegationCompleted):
            status = "✅" if event.ok else "❌"
            preview = _truncate(event.output_text or "", 500)
            return self._emit_delta({"content": f"\n\n⇠ **委派完成** {status}: {preview}\n"})

        # Tool events — delegated to ToolEventProjector
        tool_chunks = self._delegate_tool_events(stamped)
        if tool_chunks is not None:
            return tool_chunks

        # Evolve the turn snapshot
        old_snapshot = self._snapshot
        self._snapshot = self._machine.build(self._snapshot, stamped)

        # Diff snapshots → emit SSE chunks
        return self._diff(old_snapshot, self._snapshot)

    # ── Snapshot diffing ────────────────────────────────────

    def _diff(self, old: TurnSnapshot, new: TurnSnapshot) -> list[Chunk]:
        """Compute SSE chunks from the diff between two snapshots."""
        chunks: list[Chunk] = []

        # Current turn updated
        if new.turns:
            curr_idx = new.current_turn_index
            if 0 <= curr_idx < len(new.turns):
                curr = new.turns[curr_idx]
                chunks.extend(self._diff_turn(curr, curr_idx))

        # Run finished
        if new.finished and not old.finished:
            chunks.extend(self._emit_run_finished(new))

        return chunks

    def _diff_turn(self, turn: Turn, index: int) -> list[Chunk]:
        """Emit chunks for reasoning and answer text deltas."""
        chunks: list[Chunk] = []

        # Reasoning: pass-through delta (no block management)
        old_r = self._cursor.reasoning_emitted.get(index, 0)
        if len(turn.reasoning_text) > old_r:
            chunks.extend(self._emit_delta({"reasoning_content": turn.reasoning_text[old_r:]}))
            self._cursor.reasoning_emitted[index] = len(turn.reasoning_text)

        # Answer: pass-through delta
        old_a = self._cursor.answer_emitted.get(index, 0)
        if len(turn.answer_text) > old_a:
            chunks.extend(self._emit_delta({"content": turn.answer_text[old_a:]}))
            self._cursor.answer_emitted[index] = len(turn.answer_text)

        return chunks

    # ── Run lifecycle ───────────────────────────────────────

    def _emit_run_finished(self, snapshot: TurnSnapshot) -> list[Chunk]:
        """Emit final chunks when the run completes."""
        chunks: list[Chunk] = []

        # 🔴 Run error — failed runs must notify frontend
        if snapshot.status == "failed" or snapshot.error:
            error_msg = snapshot.error or f"run finished with status={snapshot.status}"
            chunks.extend(self._wrap_lca_events([lca_run_error_event(message=error_msg)]))

        # Final output fallback
        if snapshot.final_output and not any(self._cursor.answer_emitted.values()):
            chunks.extend(self._emit_delta({"content": snapshot.final_output}))

        # Finish chunk with usage + steps
        if not self._cursor.finish_emitted:
            self._cursor.finish_emitted = True
            chunks.extend(self._emit_finish(snapshot))

        return chunks

    # ── Tool event delegation ───────────────────────────────

    def _delegate_tool_events(self, stamped: StampedEvent) -> list[Chunk] | None:
        """Delegate tool lifecycle events to ToolEventProjector."""
        event = stamped.event
        # 🔴 ToolCallStreaming — early card indicator
        if isinstance(event, ToolCallStreaming):
            return self._tools.project_call_streaming(event)
        if isinstance(event, ToolStarted):
            return self._tools.project_started(event)
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
        """Adapt ToolEventProjector's list-of-deltas callback."""
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
        """Emit the final stop chunk with usage + step count."""
        usage: dict[str, int] | None = None
        if self._prompt_tokens or self._completion_tokens:
            usage = {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
            }
        chunk = self._chunk({}, finish_reason="stop", usage=usage)
        # 🟡 Step count via lca.events
        if snapshot.steps_total > 0:
            chunk = merge_lca_extension(
                chunk, [{"type": "run_meta", "steps": snapshot.steps_total}]
            )
        return [chunk]

    def _chunk(
        self,
        delta: dict[str, Any],
        *,
        finish_reason: str | None = None,
        usage: dict[str, Any] | None = None,
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


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


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
    """Stream standard OpenAI SSE chunks for LobeHub model-runtime."""
    projector = OpenAISSEProjector(chat_id=chat_id, model=model)
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
    projector = OpenAISSEProjector(chat_id=chat_id, model=model)
    parts: list[str] = []
    async for frame in frame_stream:
        for chunk in projector.project_frame(frame):
            delta = chunk["choices"][0].get("delta") or {}
            text = delta.get("content")
            if isinstance(text, str) and text:
                parts.append(text)
    return projector.completion_json("".join(parts))
