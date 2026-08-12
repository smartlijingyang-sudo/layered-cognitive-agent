"""OpenAIStreamEmitter — typed journal events → OpenAI SSE chunks.

Replaces the old three-module pipeline:
    - ``projection/openai_sse.py``  (OpenAISSEProjector)
    - ``projection/tool_events.py`` (ToolEventProjector)
    - ``lobehub_bridge/lca_sse_extension.py`` (LCA SSE extension formatting)

All three concerns are unified here because they share mutable state
(tool call indices, pending invocations, exec buffers) and the chunk
formatting is inseparable from the event dispatch.

Design principles:
    1. **Consume typed events** — no string parsing, no JSON round-trip
    2. **Mode A closed-loop** — tools execute server-side; the outward
       SSE never carries ``delta.tool_calls`` (invariant enforced by
       ``assert_finish_invariant``)
    3. **LCA extension via ``chunk["lca"]``** — tool lifecycle events
       flow to the frontend as a typed extension payload
    4. **Single responsibility per method** — each event handler is
       independent; chunk formatting is factored into helpers

Wire format (unchanged for frontend compatibility):
    Standard ``chat.completion.chunk`` with ``delta.content`` for answer
    text, ``delta.reasoning_content`` for thinking, and ``lca.events[]``
    for server-side tool lifecycle.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from typing import Any

from gateway.lobehub_bridge.file_urls import absolutize_file_parts
from gateway.lobehub_bridge.lobehub_adapter import (
    build_tool_plugin_state,
    resolve_tool_wire,
    split_wire_name,
    tool_result_content,
    tool_result_preview_limit,
    transform_tool_arguments,
)
from gateway.lobehub_bridge.lobehub_adapter.json_helpers import (
    parse_args_json,
    safe_json_string,
)
from gateway.lobehub_bridge.lobehub_adapter.protocol import TOOL_RESULT_PREVIEW_LIMIT
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DelegationCompleted,
    DelegationIssued,
    JournalEvent,
    LlmCallCompleted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    SandboxOutputDelta,
    StampedEvent,
    StepTextDelta,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.computer.constants import STREAMING_WIRE_APIS
from lca.layer1_cognitive.body.tool_ui_state import wire_arguments_json

# ── LCA SSE extension constants ───────────────────────────

_LCA_EXT_VERSION = 1
_CLOSED_LOOP = True

# ── Types ─────────────────────────────────────────────────

Chunk = dict[str, Any]
_ALLOWED_FINISH_REASONS = frozenset({None, "stop"})


# ── Tool call tracking (internal state) ───────────────────


@dataclass
class _PendingToolCall:
    """Tracks a tool call between ToolStarted and ToolInvoked."""

    tool_call_id: str
    index: int
    lca_tool_name: str
    arguments_preview: str
    wire_arguments: str = "{}"
    plugin_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class _ExecBuffer:
    """Accumulates sandbox stdout/stderr for streaming tool cards."""

    stdout: str = ""
    stderr: str = ""
    seq: int = 0


# ══════════════════════════════════════════════════════════
# OpenAIStreamEmitter
# ══════════════════════════════════════════════════════════


@dataclass
class OpenAIStreamEmitter:
    """Consumes typed journal events, emits OpenAI chat.completion.chunk dicts.

    Replaces OpenAISSEProjector + ToolEventProjector + lca_sse_extension.
    One class, one state machine, one file.

    Usage::

        emitter = OpenAIStreamEmitter(chat_id="chatcmpl-xxx", model="solo")
        async for stamped in event_bus.subscribe():
            for chunk in emitter.consume(stamped):
                yield sse_encode(chunk)
        for chunk in emitter.ensure_finished():
            yield sse_encode(chunk)
    """

    chat_id: str
    model: str

    # ── Text accumulation ───────────────────────────────
    _reasoning_text: str = ""
    _answer_text: str = ""
    _reasoning_emitted: int = 0  # cursor: how much reasoning has been sent
    _answer_emitted: int = 0  # cursor: how much answer has been sent

    # ── Run lifecycle ───────────────────────────────────
    _finished: bool = False
    _status: str = "running"
    _error: str = ""
    _final_output: str = ""
    _steps_total: int = 0

    # ── Token tracking ──────────────────────────────────
    _prompt_tokens: int = 0
    _completion_tokens: int = 0

    # ── Chunk formatting state ──────────────────────────
    _role_emitted: bool = False
    _finish_emitted: bool = False

    # ── Tool state machine ──────────────────────────────
    _tool_call_index: int = 0
    _pending_tools: dict[str, _PendingToolCall] = field(default_factory=dict)
    _invocation_tool_ids: dict[str, str] = field(default_factory=dict)
    _exec_buffers: dict[str, _ExecBuffer] = field(default_factory=dict)

    # ══════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════

    def consume(self, stamped: StampedEvent) -> list[Chunk]:
        """Process one typed journal event → list of OpenAI chunks."""
        return self._dispatch(stamped.event)

    def ensure_finished(self) -> list[Chunk]:
        """Emit a finish chunk if the run ended without one (safety net)."""
        if self._finish_emitted:
            return []
        return self._emit_finish()

    def completion_json(self, content: str, *, finish_reason: str = "stop") -> dict[str, Any]:
        """Build a non-streaming chat.completion response."""
        usage: dict[str, int] | None = None
        if self._prompt_tokens or self._completion_tokens:
            usage = {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
            }
        body: dict[str, Any] = {
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
        }
        if usage is not None:
            body["usage"] = usage
        return body

    # ══════════════════════════════════════════════════
    # Event dispatch
    # ══════════════════════════════════════════════════

    def _dispatch(self, event: JournalEvent) -> list[Chunk]:
        """Route a journal event to its handler."""
        # ── Run start: emit role chunk for immediate loading ──
        if isinstance(event, AgentRunStarted | TeamRunStarted):
            if not self._role_emitted:
                return self._emit_delta({})
            return []

        # ── Reasoning: accumulate + flush delta ─────────
        if isinstance(event, ReasoningDelta):
            return self._handle_reasoning(event)

        # ── Answer text: accumulate + flush delta ───────
        if isinstance(event, StepTextDelta):
            if event.channel == StreamChannel.ANSWER.value:
                return self._handle_answer(event)
            return [
                self._lca_chunk(
                    {},
                    {
                        "type": "StepTextDelta",
                        "channel": event.channel,
                        "text_delta": event.text_delta,
                    },
                )
            ]

        # ── Run finished: error + output + finish chunk ─
        if isinstance(event, AgentRunFinished | TeamRunFinished):
            return self._handle_run_finished(event)

        # ── Token tracking ──────────────────────────────
        if isinstance(event, LlmCallCompleted):
            self._prompt_tokens += int(event.prompt_tokens or 0)
            self._completion_tokens += int(event.completion_tokens or 0)
            return []

        # ── Reasoning boundaries (per-LLM-call thinking blocks) ──
        if isinstance(event, LlmCallStarted):
            return self._handle_llm_call_started(event)
        if isinstance(event, ReasoningCompleted):
            return self._handle_reasoning_completed(event)

        # ── Delegation: team collaboration display ──────
        if isinstance(event, DelegationIssued):
            text = f"\n\n⇢ **委派** → `{event.callee_role}`: {event.subtask_preview}\n"
            return self._emit_delta({"content": text})
        if isinstance(event, DelegationCompleted):
            status = "✅" if event.ok else "❌"
            preview = _truncate(event.output_text or "", 500)
            return self._emit_delta({"content": f"\n\n⇠ **委派完成** {status}: {preview}\n"})

        # ── Tool lifecycle ──────────────────────────────
        if isinstance(
            event,
            ToolCallStreaming | ToolStarted | SandboxOutputDelta | ToolInvoked | ToolDenied,
        ):
            return self._dispatch_tool_event(event)

        # ── Fallback: forward unknown events as lca.events ──
        # Never silently drop journal events — the frontend decides what to render.
        return [
            self._lca_chunk(
                {},
                {"type": type(event).__name__, **asdict(event)},
            )
        ]

    # ══════════════════════════════════════════════════
    # Reasoning & Answer handlers
    # ══════════════════════════════════════════════════

    def _handle_reasoning(self, event: Any) -> list[Chunk]:
        """Accumulate reasoning text and emit new delta."""
        self._reasoning_text += event.text_delta or ""
        new_len = len(self._reasoning_text)
        if new_len <= self._reasoning_emitted:
            return []
        delta_text = self._reasoning_text[self._reasoning_emitted :]
        self._reasoning_emitted = new_len
        return self._emit_delta({"reasoning_content": delta_text})

    def _handle_answer(self, event: StepTextDelta) -> list[Chunk]:
        """Accumulate answer text and emit new delta."""
        self._answer_text += event.text_delta or ""
        new_len = len(self._answer_text)
        if new_len <= self._answer_emitted:
            return []
        delta_text = self._answer_text[self._answer_emitted :]
        self._answer_emitted = new_len
        return self._emit_delta({"content": delta_text})

    def _handle_llm_call_started(self, event: LlmCallStarted) -> list[Chunk]:
        """Emit reasoning_start to signal a new thinking block on the frontend."""
        # Reset per-step reasoning accumulator so each LLM call gets its own
        # reasoning section in the UI.
        self._reasoning_text = ""
        self._reasoning_emitted = 0
        return [
            self._lca_chunk(
                {},
                {"type": "reasoning_start", "step": event.step},
            )
        ]

    def _handle_reasoning_completed(self, event: ReasoningCompleted) -> list[Chunk]:
        """Emit reasoning_section with the full text for this LLM turn."""
        # Flush any remaining reasoning text that wasn't yet sent as deltas
        chunks: list[Chunk] = []
        new_len = len(self._reasoning_text)
        if new_len > self._reasoning_emitted:
            delta_text = self._reasoning_text[self._reasoning_emitted :]
            self._reasoning_emitted = new_len
            chunks.append(self._emit_delta({"reasoning_content": delta_text})[0])

        # Emit reasoning_section so the frontend can save this as a finished
        # block and reset for the next step.
        chunks.append(
            self._lca_chunk(
                {},
                {
                    "type": "reasoning_section",
                    "step": event.step,
                    "content": self._reasoning_text,
                },
            )
        )
        # Reset per-step accumulator for the next LLM call
        self._reasoning_text = ""
        self._reasoning_emitted = 0
        return chunks

    # ══════════════════════════════════════════════════
    # Run lifecycle
    # ══════════════════════════════════════════════════

    def _handle_run_finished(self, event: AgentRunFinished | TeamRunFinished) -> list[Chunk]:
        """Handle run completion: error + final output + finish chunk."""
        self._finished = True
        self._status = event.status or "completed"
        self._error = event.error or ""
        self._final_output = event.output_text or ""
        self._steps_total = event.steps or 0

        chunks: list[Chunk] = []

        # 🔴 Run error → lca extension event
        if self._status == "failed" or self._error:
            error_msg = self._error or f"run finished with status={self._status}"
            chunks.append(
                self._lca_chunk(
                    {},
                    {
                        "type": "run_error",
                        "message": error_msg,
                        "code": "lca_run_failed",
                        "closed_loop": _CLOSED_LOOP,
                    },
                )
            )

        # Final output fallback (if no answer text was streamed)
        if self._final_output and self._answer_emitted == 0:
            chunks.extend(self._emit_delta({"content": self._final_output}))

        # Finish chunk
        if not self._finish_emitted:
            chunks.extend(self._emit_finish())

        return chunks

    # ══════════════════════════════════════════════════
    # Tool lifecycle
    # ══════════════════════════════════════════════════

    def _dispatch_tool_event(self, event: JournalEvent) -> list[Chunk]:
        """Route tool lifecycle events to handlers."""
        if isinstance(event, ToolCallStreaming):
            return self._tool_call_streaming(event)
        if isinstance(event, ToolStarted):
            return self._tool_started(event)
        if isinstance(event, SandboxOutputDelta):
            return self._sandbox_output(event)
        if isinstance(event, ToolInvoked):
            return self._tool_invoked(event)
        if isinstance(event, ToolDenied):
            return self._tool_denied(event)
        return []

    # ── ToolCallStreaming ────────────────────────────────

    def _tool_call_streaming(self, event: ToolCallStreaming) -> list[Chunk]:
        """LLM generating tool args — emit early card indicator."""
        return [
            self._lca_chunk(
                {},
                {
                    "type": "tool_call_streaming",
                    "tool_name": event.tool_name,
                    "closed_loop": _CLOSED_LOOP,
                    **({"tool_call_id": event.tool_call_id} if event.tool_call_id else {}),
                },
            )
        ]

    # ── ToolStarted ──────────────────────────────────────

    def _tool_started(self, event: ToolStarted) -> list[Chunk]:
        """Tool execution begins — emit tool_started + optional seed state."""
        idx = self._tool_call_index
        self._tool_call_index += 1
        tool_call_id = f"call_{event.invocation_id}" if event.invocation_id else f"call_{idx}"
        args_preview = event.arguments_preview or "{}"
        started_state = dict(event.plugin_state or {})

        # Resolve wire name and full arguments
        full_args_json = wire_arguments_json(
            arguments_preview=args_preview,
            plugin_state=started_state,
        )
        wire = resolve_tool_wire(event.tool_name, full_args_json)
        function_name = wire.wire_name if wire else event.tool_name
        args_json = (
            transform_tool_arguments(wire, full_args_json)
            if wire
            else safe_json_string(full_args_json)
        )
        identifier, api_name = split_wire_name(function_name)

        # Register pending tool for later correlation
        if event.invocation_id:
            self._pending_tools[event.invocation_id] = _PendingToolCall(
                tool_call_id=tool_call_id,
                index=idx,
                lca_tool_name=event.tool_name,
                arguments_preview=args_preview,
                wire_arguments=full_args_json,
                plugin_state=started_state,
            )
            self._invocation_tool_ids[event.invocation_id] = tool_call_id

        # Build tool_started event
        events: list[dict[str, Any]] = [
            {
                "type": "tool_started",
                "tool_call_id": tool_call_id,
                "wire_name": function_name,
                "identifier": identifier,
                "api_name": api_name,
                "arguments": args_json,
                "closed_loop": _CLOSED_LOOP,
                **({"lca_tool_name": event.tool_name} if event.tool_name else {}),
            }
        ]

        # Seed card state for streaming APIs (code/command visible before first delta)
        if started_state and wire and wire.api_name in STREAMING_WIRE_APIS:
            seed = dict(started_state)
            seed.setdefault("executionEnv", "sandbox")
            seed.setdefault("success", True)
            events.append(
                {
                    "type": "tool_state",
                    "tool_call_id": tool_call_id,
                    "state": seed,
                    "snapshot_seq": 0,
                    "content": "",
                }
            )

        return [self._lca_chunk({}, e) for e in events]

    # ── SandboxOutputDelta ───────────────────────────────

    def _sandbox_output(self, event: SandboxOutputDelta) -> list[Chunk]:
        """Live sandbox stdout/stderr — update streaming tool card."""
        inv_id = event.invocation_id
        if not inv_id:
            return []
        buf = self._exec_buffers.setdefault(inv_id, _ExecBuffer())
        buf.seq += 1
        if event.stream == "stderr":
            buf.stderr += event.text_delta
        else:
            buf.stdout += event.text_delta

        tool_call_id = self._invocation_tool_ids.get(inv_id)
        pending = self._pending_tools.get(inv_id)
        if not tool_call_id or pending is None:
            return []

        wire = resolve_tool_wire(pending.lca_tool_name, pending.wire_arguments)
        if wire is None or wire.api_name not in STREAMING_WIRE_APIS:
            return []

        args = wire.transform_args(parse_args_json(pending.wire_arguments))
        state: dict[str, Any] = {
            "executionEnv": "sandbox",
            "stdout": buf.stdout,
            "stderr": buf.stderr,
            "success": True,
        }
        # Preserve started fields (code/command)
        for key in ("code", "command", "language", "description"):
            if key in pending.plugin_state:
                state[key] = pending.plugin_state[key]

        if wire.api_name == "executeCode":
            state["output"] = buf.stdout
            state["language"] = args.get("language", state.get("language", "python"))
            code = args.get("code") or state.get("code")
            if isinstance(code, str) and code:
                state["code"] = code
        else:
            command = args.get("command") or state.get("command", "")
            state["command"] = command
            state["output"] = buf.stdout or buf.stderr

        return [
            self._lca_chunk(
                {},
                {
                    "type": "tool_state",
                    "tool_call_id": tool_call_id,
                    "state": state,
                    "snapshot_seq": buf.seq,
                    "content": buf.stdout or buf.stderr,
                },
            )
        ]

    # ── ToolInvoked ──────────────────────────────────────

    def _tool_invoked(self, event: ToolInvoked) -> list[Chunk]:
        """Tool execution completed — emit tool_result."""
        inv_id = event.invocation_id
        pending = self._pending_tools.pop(inv_id, None) if inv_id else None
        tool_call_id = (
            pending.tool_call_id
            if pending
            else self._invocation_tool_ids.pop(inv_id, "")
            if inv_id
            else ""
        )
        exec_buf = self._exec_buffers.pop(inv_id, None) if inv_id else None
        if inv_id:
            self._invocation_tool_ids.pop(inv_id, None)

        args_preview = event.arguments_preview or (pending.arguments_preview if pending else "{}")
        lca_name = event.tool_name or (pending.lca_tool_name if pending else "")
        wire_args = (
            pending.wire_arguments
            if pending and pending.wire_arguments
            else wire_arguments_json(
                arguments_preview=args_preview,
                plugin_state=event.plugin_state or (pending.plugin_state if pending else None),
            )
        )
        wire = resolve_tool_wire(lca_name, wire_args)

        if wire and tool_call_id:
            limit = tool_result_preview_limit(lca_name)
            preview = _truncate(event.result_preview, limit)

            # Build plugin state — prefer journal SSOT (full, untruncated)
            if event.plugin_state:
                state = dict(event.plugin_state)
                state["success"] = event.ok
                if not event.ok and event.error:
                    state["errorDetail"] = event.error
                    state.setdefault("error", event.error)
            else:
                state = build_tool_plugin_state(
                    wire,
                    arguments_preview=wire_args,
                    result_preview=preview,
                    ok=event.ok,
                    error=event.error,
                )

            # Merge exec buffer (sandbox stdout/stderr)
            if exec_buf:
                if exec_buf.stdout:
                    state["stdout"] = exec_buf.stdout
                    state.setdefault("output", exec_buf.stdout)
                if exec_buf.stderr:
                    state["stderr"] = exec_buf.stderr

            # Ensure code/command from started state if result omitted them
            if pending:
                for key in ("code", "command", "language"):
                    if key not in state and key in pending.plugin_state:
                        state[key] = pending.plugin_state[key]

            # File attachments
            file_parts = absolutize_file_parts(event.files or ())
            if file_parts:
                state["files"] = file_parts

            # Display content
            content = tool_result_content(
                preview, ok=event.ok, error=event.error, lca_tool_name=lca_name
            )
            # Skills: prefer full content from plugin_state for card body
            if lca_name == "activate_skill" and isinstance(state.get("content"), str):
                content = state["content"]
            if not content and state.get("output"):
                content = str(state["output"])[:limit]

            return [
                self._lca_chunk(
                    {},
                    {
                        "type": "tool_result",
                        "tool_call_id": tool_call_id,
                        "content": content,
                        **({"state": state} if state else {}),
                        **({"error": event.error} if not event.ok and event.error else {}),
                        **({"files": file_parts} if file_parts else {}),
                    },
                )
            ]

        # Fallback: no wire spec → render as text delta
        if event.ok:
            preview = _truncate(event.result_preview, TOOL_RESULT_PREVIEW_LIMIT)
            text = f"\n\n> **{event.tool_name}** ✅ ({event.latency_ms}ms)\n> {preview}\n"
        else:
            text = f"\n\n> **{event.tool_name}** ❌ {event.error}\n"
        return self._emit_delta({"content": text})

    # ── ToolDenied ───────────────────────────────────────

    def _tool_denied(self, event: ToolDenied) -> list[Chunk]:
        """Tool call rejected — render as text delta."""
        text = f"\n\n> **{event.tool_name}** ⛔ {event.reason}\n"
        return self._emit_delta({"content": text})

    # ══════════════════════════════════════════════════
    # Chunk formatting helpers
    # ══════════════════════════════════════════════════

    def _emit_delta(self, delta: dict[str, Any]) -> list[Chunk]:
        """Emit a content/reasoning delta chunk, auto-prepending role."""
        if not self._role_emitted:
            self._role_emitted = True
            return [self._chunk({"role": "assistant", **delta})]
        return [self._chunk(delta)]

    def _emit_finish(self) -> list[Chunk]:
        """Emit the terminal stop chunk with usage + step count."""
        self._finish_emitted = True
        usage: dict[str, int] | None = None
        if self._prompt_tokens or self._completion_tokens:
            usage = {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
            }

        chunks: list[Chunk] = []

        # run_meta as a separate lca-only chunk BEFORE the terminal stop.
        # Must NOT share a chunk with finish_reason="stop" because the
        # frontend's lca check short-circuits before processing the stop
        # signal, causing the stream to never terminate on the client.
        if self._steps_total > 0:
            meta_chunk = self._chunk({})
            meta_chunk["lca"] = {
                "v": _LCA_EXT_VERSION,
                "events": [{"type": "run_meta", "steps": self._steps_total}],
            }
            chunks.append(meta_chunk)

        # Clean terminal stop chunk — no lca wrapping
        chunks.append(self._chunk({}, finish_reason="stop", usage=usage))
        return chunks

    def _chunk(
        self,
        delta: dict[str, Any],
        *,
        finish_reason: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a standard ``chat.completion.chunk``."""
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

    def _lca_chunk(self, base: dict[str, Any], lca_event: dict[str, Any]) -> dict[str, Any]:
        """Attach an LCA extension event to a proper OpenAI chunk.

        If ``base`` is empty, builds a full chunk structure first so that
        downstream consumers always see ``choices[].delta``.
        """
        if not base:
            base = self._chunk({})
        existing = base.get("lca")
        merged_events: list[dict[str, Any]] = []
        if isinstance(existing, dict) and isinstance(existing.get("events"), list):
            merged_events.extend(existing["events"])
        merged_events.append(lca_event)
        return {
            **base,
            "lca": {"v": _LCA_EXT_VERSION, "events": merged_events},
        }


# ══════════════════════════════════════════════════════════
# Module-level streaming helpers
# ══════════════════════════════════════════════════════════


async def stream_openai_chunks(
    event_stream: AsyncIterator[StampedEvent],
    *,
    chat_id: str,
    model: str,
) -> AsyncIterator[bytes]:
    """Stream OpenAI SSE chunks from a typed event bus subscription.

    Replaces the old ``stream_openai_from_run`` which consumed SSE text frames.
    This version receives typed ``StampedEvent`` objects directly — no parsing.
    """
    emitter = OpenAIStreamEmitter(chat_id=chat_id, model=model)
    async for stamped in event_stream:
        for chunk in emitter.consume(stamped):
            yield b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"
    # Safety net: ensure the stream always terminates
    for chunk in emitter.ensure_finished():
        yield b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"
    yield b"data: [DONE]\n\n"


async def collect_openai_completion(
    event_stream: AsyncIterator[StampedEvent],
    *,
    chat_id: str,
    model: str,
) -> dict[str, Any]:
    """Non-streaming: collect all content into a single completion response."""
    emitter = OpenAIStreamEmitter(chat_id=chat_id, model=model)
    parts: list[str] = []
    async for stamped in event_stream:
        for chunk in emitter.consume(stamped):
            delta = chunk["choices"][0].get("delta") or {}
            text = delta.get("content")
            if isinstance(text, str) and text:
                parts.append(text)
    return emitter.completion_json("".join(parts))


def assert_finish_invariant(chunks: list[dict[str, Any]]) -> None:
    """Mode A contract: outward SSE must never signal tool-loop continuation.

    - No ``finish_reason`` other than ``None`` or ``"stop"``
    - No ``delta.tool_calls`` (would trigger LobeHub's client-side loop)
    - Exactly one stop chunk
    """
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


# ══════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
