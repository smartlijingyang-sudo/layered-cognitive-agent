"""Project LCA journal SSE frames → OpenAI chat.completion chunks (LobeHub G2A).

.. deprecated::
    This module is superseded by ``gateway.presentation`` + ``gateway.projection``.
    New code should use ``DiffProjector`` from ``gateway.projection.diff_projector``.
    This module is kept for passthrough scenarios (non-journal LLM proxy) only.

LobeHub Mode A (closed-loop) contract:
- ``delta.content`` — user-visible prose only (never raw Decision JSON)
- ``delta.reasoning_content`` — Thinking panel
- ``lca.events`` — full server-side tool lifecycle (``tool_started`` / ``tool_result`` / ``tool_state``)
- **Never** ``delta.tool_calls`` — that triggers LobeHub ``GeneralChatAgent`` client tool loop
  and duplicates LCA runs for a single user turn.

Rendering order (matches native LobeHub):
    reasoning → tool cards → answer text

In native LobeHub the model only produces answer text AFTER tool execution.
In Mode A closed-loop, the LLM's ``response_text`` is extracted during
streaming (before tool execution).  The projector buffers this text and
releases it at the correct point in the event stream so the frontend
renders tool cards ABOVE answer text, not below.

Content sources (priority order):
1. ``StepTextDelta`` channel ``answer`` — streamed ``response_text`` extracts
2. ``DecisionMade.response_text`` — canonical when stream absent for step
3. ``SynthesisCompleted`` / ``*RunFinished.output_text`` — team / fallback
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
    lca_run_error_event,
    lca_tool_call_streaming_event,
    merge_lca_extension,
)
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    DelegationCompleted,
    DelegationIssued,
    LlmCallCompleted,
    ReasoningCompleted,
    ReasoningDelta,
    SandboxOutputDelta,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

USER_FACING_TERMINAL_ACTIONS = frozenset({"respond", "stop", "ask_human"})
_ALLOWED_FINISH_REASONS = frozenset({None, "stop"})
_DELEGATION_PREVIEW_LEN = 500


# ── SSE frame parsing ───────────────────────────────────────


def parse_sse_frame_record(frame: str) -> dict[str, Any] | None:
    """Extract JSON record from a journal SSE frame."""
    for line in frame.splitlines():
        if line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


def extract_user_question(messages: list[Any]) -> str:
    """Last user message text from OpenAI-style messages."""
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            text = content.strip()
            if text:
                return text
        elif isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    text = str(part.get("text", "")).strip()
                    if text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)
    return ""


def resolve_lca_mode(model: str) -> str:
    """Map OpenAI model id → LCA gateway mode."""
    key = model.strip().lower()
    if key in {"team", "auto"}:
        return "team"
    return "solo"


# ── Main projector ──────────────────────────────────────────


@dataclass
class JournalOpenAiProjector:
    """Stateful journal → OpenAI SSE chunk projector (LobeHub Mode A closed-loop).

    Tool lifecycle projection is delegated to ``ToolProjectionHandler``;
    this class handles text / reasoning / delegation / run events and
    owns the chunk-formatting primitives.

    **Event reordering**: native LobeHub renders reasoning → tool cards →
    answer text.  In Mode A, answer text (``StepTextDelta`` channel=answer)
    arrives during LLM streaming, BEFORE tool execution.  The projector
    buffers this text and releases it at the correct point:

    - Tool steps: after ``ToolInvoked`` (tool card closed)
    - Direct response steps: after ``LlmCallCompleted`` (LLM done)
    - Run end: safety net flush
    """

    chat_id: str
    model: str
    _step_buffers: dict[str, str] = field(default_factory=dict)
    _reasoning_buffers: dict[str, str] = field(default_factory=dict)
    _sent_role: bool = False
    _finished: bool = False
    _content_emitted: bool = False
    _run_failed: bool = False
    _run_error: str = ""
    _prompt_tokens: int = 0
    _completion_tokens: int = 0
    _steps_answer_streamed: set[int] = field(default_factory=set)
    _reasoning_step: dict[str, int] = field(default_factory=dict)
    _tools: ToolProjection = field(init=False)
    # Answer text buffer — holds text until tool lifecycle completes
    _answer_buffer: str = field(default="", init=False)
    _answer_buffer_active: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._tools = ToolProjection(
            emit_lca=self._emit_lca_events,
            emit_delta=self._emit_delta_parts,
        )

    def _emit_delta_parts(self, parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Adapt ToolProjection list-of-deltas callback to ``_emit_delta``."""
        chunks: list[dict[str, Any]] = []
        for part in parts:
            chunks.extend(self._emit_delta(part))
        return chunks

    # ── Frame dispatch ──────────────────────────────────────

    def project_frame(self, frame: str) -> list[dict[str, Any]]:
        if self._finished:
            return []
        record = parse_sse_frame_record(frame)
        if record is None:
            return []
        try:
            stamped = record_to_stamped(record)
        except Exception:
            return []
        if stamped is None:
            return []

        event = stamped.event

        if isinstance(event, ReasoningDelta):
            return self._project_reasoning(event, stamped.scope.run_id)
        if isinstance(event, ReasoningCompleted):
            return self._project_reasoning_completed(event)
        if isinstance(event, StepTextDelta):
            return self._project_step_text(event, stamped.scope.run_id)
        if isinstance(event, StepCompleted):
            return self._project_step_completed(event)
        if isinstance(event, TeamRunStarted | AgentRunStarted):
            return self._project_run_started(event)
        if isinstance(event, AgentRunFinished | TeamRunFinished):
            return self._project_run_finished(event)

        # Tool call streaming — early indicator that LLM is generating args.
        # Close the reasoning block so thinking appears BEFORE the tool card,
        # matching native LobeHub's interleaved rendering.
        if isinstance(event, ToolCallStreaming):
            return self._project_tool_call_streaming(event)

        # Tool lifecycle — delegated (with answer buffer flush after result)
        if isinstance(event, ToolStarted):
            return self._tools.project_started(event)
        if isinstance(event, SandboxOutputDelta):
            return self._tools.project_sandbox_output(event)
        if isinstance(event, ToolInvoked):
            chunks = self._tools.project_invoked(event)
            # After tool completes, flush buffered answer text so it appears
            # AFTER the tool card — matching native LobeHub rendering order.
            chunks.extend(self._flush_answer_buffer())
            return chunks
        if isinstance(event, ToolDenied):
            return self._tools.project_denied(event)

        # Collaboration events
        if isinstance(event, DelegationIssued):
            return self._project_delegation_issued(event)
        if isinstance(event, DelegationCompleted):
            return self._project_delegation_completed(event)

        # Cognitive events
        if isinstance(event, DecisionMade):
            return self._project_decision(event)
        if isinstance(event, SynthesisCompleted):
            return self._project_synthesis(event)

        # Resource accounting + flush trigger for direct-response steps
        if isinstance(event, LlmCallCompleted):
            self._prompt_tokens += int(event.prompt_tokens)
            self._completion_tokens += int(event.completion_tokens)
            # For direct-response steps (no tool), flush answer text now
            # so it appears immediately after reasoning completes.
            return self._flush_answer_buffer()

        return []

    # ── Text / reasoning ────────────────────────────────────

    def _project_reasoning(self, event: ReasoningDelta, run_id: str) -> list[dict[str, Any]]:
        key = f"{run_id}:reasoning"
        prev_step = self._reasoning_step.get(key, -1)
        current_step = event.step or 0
        chunks: list[dict[str, Any]] = []

        # Step boundary: close previous reasoning block, open new one.
        # This creates separate collapsible "已深度思考" sections per step,
        # matching native LobeHub's per-turn reasoning display.
        if current_step != prev_step:
            if prev_step >= 0:
                chunks.extend(self._emit_lca_event({"type": "reasoning_end", "step": prev_step}))
            self._reasoning_step[key] = current_step
            chunks.extend(
                self._emit_lca_event(
                    {
                        "type": "reasoning_start",
                        "step": current_step,
                    }
                )
            )

        self._reasoning_buffers[key] = self._reasoning_buffers.get(key, "") + event.text_delta
        if event.text_delta:
            chunks.extend(self._emit_delta({"reasoning_content": event.text_delta}))
        return chunks

    def _project_reasoning_completed(self, event: ReasoningCompleted) -> list[dict[str, Any]]:
        """Close the reasoning block and emit a reasoning_section event.

        Uses ``event.content_preview`` (already accumulated by the telemetry
        adapter) — no extra buffering needed. The frontend saves this as a
        finished "已深度思考" block and resets for the next step.
        """
        step = event.step
        content = event.content_preview or ""
        chunks: list[dict[str, Any]] = []
        chunks.extend(self._emit_lca_event({"type": "reasoning_end", "step": step}))
        if content:
            section_event = lca_reasoning_section_event(step=step, content=content)
            chunks.extend(self._emit_lca_events([section_event]))
        return chunks

    def _project_tool_call_streaming(self, event: ToolCallStreaming) -> list[dict[str, Any]]:
        """LLM is generating tool call arguments — emit early card indicator.

        This closes any open reasoning block so the thinking section appears
        complete before the tool card, matching native LobeHub's interleaved
        rendering: [thinking] → [tool card] → [thinking] → [tool card].
        """
        chunks: list[dict[str, Any]] = []
        # Close reasoning block if still open (ensures thinking appears
        # before tool card, not merged with it).
        for key in list(self._reasoning_step):
            step = self._reasoning_step[key]
            chunks.extend(self._emit_lca_event({"type": "reasoning_end", "step": step}))
        self._reasoning_step.clear()
        # Emit the streaming indicator so frontend shows a pending tool card.
        streaming_event = lca_tool_call_streaming_event(
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
        )
        chunks.extend(self._emit_lca_events([streaming_event]))
        return chunks

    def _project_step_text(self, event: StepTextDelta, run_id: str) -> list[dict[str, Any]]:
        channel = event.channel or StreamChannel.DECISION.value
        key = f"{run_id}:{event.step}:{channel}"
        self._step_buffers[key] = self._step_buffers.get(key, "") + event.text_delta
        if channel != StreamChannel.ANSWER.value or not event.text_delta:
            return []
        self._steps_answer_streamed.add(event.step)
        self._content_emitted = True
        # Buffer answer text — it will be released at the correct point:
        # after tool cards (tool steps) or after LlmCallCompleted (direct).
        # This ensures the native LobeHub rendering order:
        #   reasoning → tool cards → answer text
        self._answer_buffer += event.text_delta
        self._answer_buffer_active = True
        return []

    def _project_step_completed(self, event: StepCompleted) -> list[dict[str, Any]]:
        """Flush answer buffer at step boundary (safety net)."""
        return self._flush_answer_buffer()

    def _flush_answer_buffer(self) -> list[dict[str, Any]]:
        """Release buffered answer text as content deltas.

        Called at the correct point in the event stream so answer text
        appears AFTER reasoning and tool cards.
        """
        if not self._answer_buffer_active or not self._answer_buffer:
            return []
        text = self._answer_buffer
        self._answer_buffer = ""
        self._answer_buffer_active = False
        return self._emit_delta({"content": text})

    # ── Collaboration ───────────────────────────────────────

    def _project_delegation_issued(self, event: DelegationIssued) -> list[dict[str, Any]]:
        text = f"\n\n⇢ **委派** → `{event.callee_role}`: {event.subtask_preview}\n"
        return self._emit_delta({"content": text})

    def _project_delegation_completed(self, event: DelegationCompleted) -> list[dict[str, Any]]:
        status = "✅" if event.ok else "❌"
        preview = _truncate(event.output_text, _DELEGATION_PREVIEW_LEN)
        text = f"\n\n⇠ **委派完成** {status}: {preview}\n"
        return self._emit_delta({"content": text})

    # ── Cognitive ───────────────────────────────────────────

    def _project_decision(self, event: DecisionMade) -> list[dict[str, Any]]:
        if event.action_type not in USER_FACING_TERMINAL_ACTIONS:
            return []
        # For terminal actions, flush any buffered answer text first
        chunks: list[dict[str, Any]] = []
        chunks.extend(self._flush_answer_buffer())
        if event.step in self._steps_answer_streamed:
            return chunks
        text = (event.response_text or "").strip()
        if text:
            self._content_emitted = True
            chunks.extend(self._emit_delta({"content": text}))
        return chunks

    def _project_synthesis(self, event: SynthesisCompleted) -> list[dict[str, Any]]:
        if not self._content_emitted:
            text = (event.output_text or "").strip()
            if text:
                self._content_emitted = True
                return self._emit_delta({"content": text})
        return []

    # ── Run lifecycle ───────────────────────────────────────

    def _project_run_started(self, event: TeamRunStarted | AgentRunStarted) -> list[dict[str, Any]]:
        if not self._sent_role:
            return self._emit_delta({})
        return []

    def _project_run_finished(
        self, event: AgentRunFinished | TeamRunFinished
    ) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        status = getattr(event, "status", "completed")
        error = (getattr(event, "error", None) or "").strip()
        if status == "failed" or error:
            self._run_failed = True
            self._run_error = error or f"run finished with status={status}"
            chunks.extend(self._emit_lca_events([lca_run_error_event(message=self._run_error)]))
        # Safety net: flush any remaining buffered answer text
        chunks.extend(self._flush_answer_buffer())
        if not self._content_emitted:
            text = (event.output_text or "").strip()
            if text:
                self._content_emitted = True
                chunks.extend(self._emit_delta({"content": text}))
        chunks.extend(self._emit_finish())
        return chunks

    # ── Chunk formatting primitives ─────────────────────────

    def _emit_delta(self, delta: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._sent_role:
            chunk = self._chunk({"role": "assistant", **delta})
            self._sent_role = True
            return [chunk]
        return [self._chunk(delta)]

    def _emit_lca_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [merge_lca_extension(self._chunk({}), events)]

    def _emit_lca_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        return self._emit_lca_events([event])

    def _emit_finish(self) -> list[dict[str, Any]]:
        if self._finished:
            return []
        self._finished = True
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
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
    projector = JournalOpenAiProjector(chat_id=chat_id, model=model)
    async for frame in frame_stream:
        for chunk in projector.project_frame(frame):
            yield b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"
    if not projector._finished:
        for chunk in projector._emit_finish():
            yield b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"
    yield b"data: [DONE]\n\n"


async def collect_openai_completion(
    frame_stream: AsyncIterator[str],
    *,
    chat_id: str,
    model: str,
) -> dict[str, Any]:
    projector = JournalOpenAiProjector(chat_id=chat_id, model=model)
    parts: list[str] = []
    async for frame in frame_stream:
        for chunk in projector.project_frame(frame):
            delta = chunk["choices"][0].get("delta") or {}
            text = delta.get("content")
            if isinstance(text, str) and text:
                parts.append(text)
    if not projector._finished:
        projector._emit_finish()
    return projector.completion_json("".join(parts))
