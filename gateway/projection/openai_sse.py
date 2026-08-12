"""OpenAISSEProjector — journal events → OpenAI SSE chunks.

Direct event-to-chunk mapping. No intermediate representation.

Handles:
    - ReasoningDelta      → reasoning_content delta (real-time)
    - StepTextDelta       → content delta (answer channel only)
    - AgentRunFinished    → run_error + finish chunk + steps
    - DelegationIssued    → content (team collaboration)
    - Tool events         → delegated to ToolEventProjector
    - LlmCallCompleted    → token tracking

Everything else is ignored.
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
from gateway.projection.tool_events import ToolEventProjector
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DelegationCompleted,
    DelegationIssued,
    LlmCallCompleted,
    ReasoningDelta,
    SandboxOutputDelta,
    StepTextDelta,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

# ── Types ───────────────────────────────────────────────────

Chunk = dict[str, Any]
_ALLOWED_FINISH_REASONS = frozenset({None, "stop"})


# ── OpenAISSEProjector ─────────────────────────────────────


@dataclass
class OpenAISSEProjector:
    """Journal events → OpenAI SSE chunks. Direct mapping, no indirection."""

    chat_id: str
    model: str

    # Accumulated text
    _reasoning_text: str = ""
    _answer_text: str = ""

    # Emission cursors (how much has been sent as SSE delta)
    _reasoning_emitted: int = 0
    _answer_emitted: int = 0

    # Run lifecycle
    _finished: bool = False
    _status: str = "running"
    _error: str = ""
    _final_output: str = ""
    _steps_total: int = 0

    # Tokens
    _prompt_tokens: int = 0
    _completion_tokens: int = 0

    # Chunk formatting state
    _role_emitted: bool = False
    _finish_emitted: bool = False

    # Tool delegation
    _tools: ToolEventProjector = field(init=False)

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

        # ── Run started: emit role chunk for immediate loading ──
        if isinstance(event, AgentRunStarted | TeamRunStarted):
            if not self._role_emitted:
                return self._emit_delta({})
            return []

        # ── Reasoning: accumulate + emit delta ──────────────
        if isinstance(event, ReasoningDelta):
            self._reasoning_text += event.text_delta or ""
            return self._flush_reasoning()

        # ── Answer text: accumulate + emit delta ────────────
        if isinstance(event, StepTextDelta):
            if event.channel == StreamChannel.ANSWER.value:
                self._answer_text += event.text_delta or ""
                return self._flush_answer()
            return []  # decision channel — ignored

        # ── Run finished: error + output + finish chunk ─────
        if isinstance(event, AgentRunFinished | TeamRunFinished):
            return self._handle_run_finished(event)

        # ── Token tracking ──────────────────────────────────
        if isinstance(event, LlmCallCompleted):
            self._prompt_tokens += int(event.prompt_tokens or 0)
            self._completion_tokens += int(event.completion_tokens or 0)
            return []

        # ── Delegation: team collaboration display ──────────
        if isinstance(event, DelegationIssued):
            text = f"\n\n⇢ **委派** → `{event.callee_role}`: {event.subtask_preview}\n"
            return self._emit_delta({"content": text})
        if isinstance(event, DelegationCompleted):
            status = "✅" if event.ok else "❌"
            preview = _truncate(event.output_text or "", 500)
            return self._emit_delta({"content": f"\n\n⇠ **委派完成** {status}: {preview}\n"})

        # ── Tool events: delegated ──────────────────────────
        return self._delegate_tool_event(event)

    # ── Flush accumulated text as deltas ────────────────────

    def _flush_reasoning(self) -> list[Chunk]:
        """Emit new reasoning text as reasoning_content delta."""
        new_len = len(self._reasoning_text)
        if new_len <= self._reasoning_emitted:
            return []
        delta_text = self._reasoning_text[self._reasoning_emitted :]
        self._reasoning_emitted = new_len
        return self._emit_delta({"reasoning_content": delta_text})

    def _flush_answer(self) -> list[Chunk]:
        """Emit new answer text as content delta."""
        new_len = len(self._answer_text)
        if new_len <= self._answer_emitted:
            return []
        delta_text = self._answer_text[self._answer_emitted :]
        self._answer_emitted = new_len
        return self._emit_delta({"content": delta_text})

    # ── Run lifecycle ───────────────────────────────────────

    def _handle_run_finished(self, event: AgentRunFinished | TeamRunFinished) -> list[Chunk]:
        """Handle run completion: error + final output + finish chunk."""
        self._finished = True
        self._status = event.status or "completed"
        self._error = event.error or ""
        self._final_output = event.output_text or ""
        self._steps_total = event.steps or 0

        chunks: list[Chunk] = []

        # 🔴 Run error
        if self._status == "failed" or self._error:
            error_msg = self._error or f"run finished with status={self._status}"
            chunks.extend(self._wrap_lca_events([lca_run_error_event(message=error_msg)]))

        # Final output fallback (if no answer text was streamed)
        if self._final_output and self._answer_emitted == 0:
            chunks.extend(self._emit_delta({"content": self._final_output}))

        # Finish chunk
        if not self._finish_emitted:
            self._finish_emitted = True
            chunks.extend(self._emit_finish())

        return chunks

    # ── Tool event delegation ───────────────────────────────

    def _delegate_tool_event(self, event: Any) -> list[Chunk]:
        """Delegate tool lifecycle events to ToolEventProjector."""
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
        return []

    # ── Chunk formatting ────────────────────────────────────

    def _emit_delta(self, delta: dict[str, Any]) -> list[Chunk]:
        """Emit a content/reasoning delta chunk."""
        if not self._role_emitted:
            self._role_emitted = True
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

    def _emit_finish(self) -> list[Chunk]:
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
        if self._steps_total > 0:
            chunk = merge_lca_extension(chunk, [{"type": "run_meta", "steps": self._steps_total}])
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
    if not projector._finish_emitted:
        for chunk in projector._emit_finish():
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
