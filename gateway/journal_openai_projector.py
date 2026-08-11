"""Project LCA journal SSE frames → OpenAI chat.completion chunks (LobeHub G2A).

LobeHub Mode A (closed-loop) contract:
- ``delta.content`` — user-visible prose only (never raw Decision JSON)
- ``delta.reasoning_content`` — Thinking panel
- ``lca.events`` — full server-side tool lifecycle (``tool_started`` / ``tool_result`` / ``tool_state``)
- **Never** ``delta.tool_calls`` — that triggers LobeHub ``GeneralChatAgent`` client tool loop
  and duplicates LCA runs for a single user turn.

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

from gateway.lobehub_bridge.lca_sse_extension import (
    lca_run_error_event,
    lca_tool_result_event,
    lca_tool_started_event,
    lca_tool_state_event,
    merge_lca_extension,
)
from gateway.lobehub_bridge.tool_wire import (
    build_tool_plugin_state,
    resolve_tool_wire,
    split_wire_name,
    tool_result_content,
    tool_result_preview_limit,
    transform_tool_arguments,
)
from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    DelegationCompleted,
    DelegationIssued,
    LlmCallCompleted,
    ReasoningDelta,
    SandboxOutputDelta,
    StepTextDelta,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.computer.constants import STREAMING_WIRE_APIS
from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

USER_FACING_TERMINAL_ACTIONS = frozenset({"respond", "stop", "ask_human"})
_TOOL_RESULT_MAX_LEN = 500
_ALLOWED_FINISH_REASONS = frozenset({None, "stop"})


@dataclass
class _PendingToolCall:
    tool_call_id: str
    index: int
    lca_tool_name: str
    arguments_preview: str


@dataclass
class _ExecBuffer:
    stdout: str = ""
    stderr: str = ""
    seq: int = 0


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


@dataclass
class JournalOpenAiProjector:
    """Stateful journal → OpenAI SSE chunk projector (LobeHub Mode A closed-loop).

    Tools are projected exclusively via ``lca.events`` so LobeHub renders native
    cards without entering its client-side ``call_tool → call_llm`` loop.
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
    _tool_call_index: int = 0
    _pending_tools: dict[str, _PendingToolCall] = field(default_factory=dict)
    _invocation_tool_ids: dict[str, str] = field(default_factory=dict)
    _exec_buffers: dict[str, _ExecBuffer] = field(default_factory=dict)
    _steps_answer_streamed: set[int] = field(default_factory=set)

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
        chunks: list[dict[str, Any]] = []

        if isinstance(event, ReasoningDelta):
            chunks.extend(self._project_reasoning(event, stamped.scope.run_id))

        elif isinstance(event, StepTextDelta):
            chunks.extend(self._project_step_text(event, stamped.scope.run_id))

        elif isinstance(event, ToolStarted):
            chunks.extend(self._project_tool_started(event))

        elif isinstance(event, SandboxOutputDelta):
            chunks.extend(self._project_sandbox_output(event))

        elif isinstance(event, ToolInvoked):
            chunks.extend(self._project_tool_invoked(event))

        elif isinstance(event, ToolDenied):
            chunks.extend(self._project_tool_denied(event))

        elif isinstance(event, DelegationIssued):
            chunks.extend(self._project_delegation_issued(event))

        elif isinstance(event, DelegationCompleted):
            chunks.extend(self._project_delegation_completed(event))

        elif isinstance(event, DecisionMade):
            chunks.extend(self._project_decision(event))

        elif isinstance(event, SynthesisCompleted):
            chunks.extend(self._project_synthesis(event))

        elif isinstance(event, LlmCallCompleted):
            self._prompt_tokens += int(event.prompt_tokens)
            self._completion_tokens += int(event.completion_tokens)

        elif isinstance(event, TeamRunStarted | AgentRunStarted):
            chunks.extend(self._project_run_started(event))

        elif isinstance(event, AgentRunFinished | TeamRunFinished):
            chunks.extend(self._project_run_finished(event))

        return chunks

    def _project_reasoning(self, event: ReasoningDelta, run_id: str) -> list[dict[str, Any]]:
        key = f"{run_id}:reasoning"
        self._reasoning_buffers[key] = self._reasoning_buffers.get(key, "") + event.text_delta
        if event.text_delta:
            return self._emit_delta({"reasoning_content": event.text_delta})
        return []

    def _project_step_text(self, event: StepTextDelta, run_id: str) -> list[dict[str, Any]]:
        channel = event.channel or StreamChannel.DECISION.value
        key = f"{run_id}:{event.step}:{channel}"
        self._step_buffers[key] = self._step_buffers.get(key, "") + event.text_delta
        if channel != StreamChannel.ANSWER.value or not event.text_delta:
            return []
        self._steps_answer_streamed.add(event.step)
        self._content_emitted = True
        return self._emit_delta({"content": event.text_delta})

    def _project_tool_started(self, event: ToolStarted) -> list[dict[str, Any]]:
        idx = self._tool_call_index
        self._tool_call_index += 1
        tool_call_id = f"call_{event.invocation_id}" if event.invocation_id else f"call_{idx}"
        args_preview = event.arguments_preview or "{}"
        wire = resolve_tool_wire(event.tool_name, args_preview)
        function_name = wire.wire_name if wire else event.tool_name
        args_json = (
            transform_tool_arguments(wire, args_preview)
            if wire
            else _safe_json_string(args_preview)
        )
        identifier, api_name = split_wire_name(function_name)
        if event.invocation_id:
            pending = _PendingToolCall(
                tool_call_id=tool_call_id,
                index=idx,
                lca_tool_name=event.tool_name,
                arguments_preview=args_preview,
            )
            self._pending_tools[event.invocation_id] = pending
            self._invocation_tool_ids[event.invocation_id] = tool_call_id
        started = lca_tool_started_event(
            tool_call_id=tool_call_id,
            wire_name=function_name,
            identifier=identifier,
            api_name=api_name,
            arguments=args_json,
            lca_tool_name=event.tool_name,
        )
        return self._emit_lca_events([started])

    def _project_sandbox_output(self, event: SandboxOutputDelta) -> list[dict[str, Any]]:
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
        wire = resolve_tool_wire(pending.lca_tool_name, pending.arguments_preview)
        if wire is None or wire.api_name not in STREAMING_WIRE_APIS:
            return []
        args = wire.transform_args(_parse_args_json(pending.arguments_preview))
        state: dict[str, Any] = {
            "executionEnv": "sandbox",
            "stdout": buf.stdout,
            "stderr": buf.stderr,
            "success": True,
        }
        if wire.api_name == "executeCode":
            state["output"] = buf.stdout
            state["language"] = args.get("language", "python")
        else:
            state["command"] = args.get("command", "")
        lca_event = lca_tool_state_event(
            tool_call_id=tool_call_id,
            state=state,
            snapshot_seq=buf.seq,
        )
        return self._emit_lca_events([lca_event])

    def _project_tool_invoked(self, event: ToolInvoked) -> list[dict[str, Any]]:
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
        wire = resolve_tool_wire(lca_name, args_preview)

        if wire and tool_call_id:
            limit = tool_result_preview_limit(lca_name)
            preview = _truncate(event.result_preview, limit)
            if event.plugin_state:
                state = dict(event.plugin_state)
                state["success"] = event.ok
                if not event.ok and event.error:
                    state["errorDetail"] = event.error
            else:
                state = build_tool_plugin_state(
                    wire,
                    arguments_preview=args_preview,
                    result_preview=preview,
                    ok=event.ok,
                    error=event.error,
                )
            if exec_buf:
                if exec_buf.stdout:
                    state["stdout"] = exec_buf.stdout
                if exec_buf.stderr:
                    state["stderr"] = exec_buf.stderr
            content = tool_result_content(
                preview, ok=event.ok, error=event.error, lca_tool_name=lca_name
            )
            lca_event = lca_tool_result_event(
                tool_call_id=tool_call_id,
                content=content,
                state=state,
                error=event.error if not event.ok else None,
            )
            return self._emit_lca_events([lca_event])

        if event.ok:
            preview = _truncate(event.result_preview, _TOOL_RESULT_MAX_LEN)
            text = f"\n\n> **{event.tool_name}** ✅ ({event.latency_ms}ms)\n> {preview}\n"
        else:
            text = f"\n\n> **{event.tool_name}** ❌ {event.error}\n"
        return self._emit_delta({"content": text})

    def _project_tool_denied(self, event: ToolDenied) -> list[dict[str, Any]]:
        text = f"\n\n> **{event.tool_name}** ⛔ {event.reason}\n"
        return self._emit_delta({"content": text})

    def _project_delegation_issued(self, event: DelegationIssued) -> list[dict[str, Any]]:
        text = f"\n\n⇢ **委派** → `{event.callee_role}`: {event.subtask_preview}\n"
        return self._emit_delta({"content": text})

    def _project_delegation_completed(self, event: DelegationCompleted) -> list[dict[str, Any]]:
        status = "✅" if event.ok else "❌"
        preview = _truncate(event.output_text, _TOOL_RESULT_MAX_LEN)
        text = f"\n\n⇠ **委派完成** {status}: {preview}\n"
        return self._emit_delta({"content": text})

    def _project_decision(self, event: DecisionMade) -> list[dict[str, Any]]:
        if event.action_type not in USER_FACING_TERMINAL_ACTIONS:
            return []
        if event.step in self._steps_answer_streamed:
            return []
        text = (event.response_text or "").strip()
        if text:
            self._content_emitted = True
            return self._emit_delta({"content": text})
        return []

    def _project_synthesis(self, event: SynthesisCompleted) -> list[dict[str, Any]]:
        if not self._content_emitted:
            text = (event.output_text or "").strip()
            if text:
                self._content_emitted = True
                return self._emit_delta({"content": text})
        return []

    def _project_run_started(self, event: TeamRunStarted | AgentRunStarted) -> list[dict[str, Any]]:
        """Emit initial role chunk on run start (LobeHub ``stream_start`` alignment).

        确保 LobeHub 在收到内容之前就能创建 assistant message 占位。
        """
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
        if not self._content_emitted:
            text = (event.output_text or "").strip()
            if text:
                self._content_emitted = True
                chunks.extend(self._emit_delta({"content": text}))
        chunks.extend(self._emit_finish())
        return chunks

    def _emit_delta(self, delta: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self._sent_role:
            out.append(self._chunk({"role": "assistant", **delta}))
            self._sent_role = True
            return out
        out.append(self._chunk(delta))
        return out

    def _emit_lca_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [merge_lca_extension(self._chunk({}), events)]

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
        usage: dict[str, int] | None = None,
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


def _parse_args_json(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_json_string(raw: str) -> str:
    """Ensure arguments preview is valid JSON string for OpenAI tool_calls delta."""
    raw = (raw or "").strip()
    if not raw:
        return "{}"
    try:
        json.loads(raw)
        return raw
    except (json.JSONDecodeError, ValueError):
        return json.dumps({"preview": raw[:200]})


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

    Each frame is a nameless ``data: {chat.completion.chunk}`` line with
    optional ``lca`` extension for tool events.  The LobeHub backend's
    OpenAI SDK parses these into ``ChatCompletionChunk`` objects; the
    patched ``transformQwenStream`` / ``transformOpenAIStream`` extracts
    ``lca.events`` for tool-card rendering.
    """
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
