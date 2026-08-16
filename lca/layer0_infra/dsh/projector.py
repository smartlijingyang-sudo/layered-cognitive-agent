"""DSH session events → Journal events. Visitor over event type."""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    StepTextDelta,
    ToolInvoked,
    ToolStarted,
)
from lca.layer0_infra.dsh.mapping import project_tool_call, project_tool_result
from lca.layer0_infra.dsh.models import DshNotification
from lca.layer0_infra.dsh.ports import DshEventSink

_JSON = dict[str, Any]


class DshJournalProjector:
    """Stateful fold: one DSH session onto one Journal turn."""

    def __init__(self, sink: DshEventSink) -> None:
        self._sink = sink
        self._seq = 0
        self._step = 1
        self._opened = False
        self._finished = False
        self._open_args: dict[str, tuple[str, str]] = {}
        self._turn_status: str | None = None
        self._turn_error: str = ""
        self._handlers = {
            "turn/start": self._on_turn_start,
            "step/start": self._on_step_start,
            "request/header": self._on_request_header,
            "assistant/chunk": self._on_assistant_chunk,
            "tool/call": self._on_tool_call,
            "tool/result": self._on_tool_result,
            "turn/end": self._on_turn_end,
        }

    def feed(self, notification: DshNotification) -> None:
        event = notification.session_event
        if event is None:
            return
        event_type = str(event.get("type") or "")
        handler = self._handlers.get(event_type)
        if handler is None:
            return
        data = event.get("data")
        handler(data if isinstance(data, dict) else {})

    def ensure_open(self) -> None:
        """Emit AgentRunStarted before the first SDK notification arrives."""
        self._ensure_open()

    def emit_terminal_event(
        self, *, status: str | None = None, output: str = "", error: str = ""
    ) -> None:
        """Translate DSH turn result into a Journal AgentRunFinished via sink.

        Not an independent state write — goes through ``sink.emit`` → ``store.append``.
        """
        if self._finished:
            return
        self._ensure_open()
        self._finished = True
        final_status = status if status is not None else (self._turn_status or "completed")
        final_error = error if error else self._turn_error
        self._sink.emit(
            AgentRunFinished(
                status=final_status, output_text=output, error=final_error, steps=self._step
            )
        )

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _ensure_open(self) -> None:
        if self._opened:
            return
        self._opened = True
        self._sink.emit(AgentRunStarted(agent_role="dsh", strategy_key="dsh"))
        self._sink.emit(LlmCallStarted(step=self._step, model="dsh"))

    def _on_turn_start(self, data: _JSON) -> None:
        del data
        self._ensure_open()

    def _on_step_start(self, data: _JSON) -> None:
        step = data.get("step")
        if isinstance(step, int) and step > 0:
            self._step = step
        self._ensure_open()

    def _on_request_header(self, data: _JSON) -> None:
        del data
        self._ensure_open()

    def _on_assistant_chunk(self, data: _JSON) -> None:
        self._ensure_open()
        step = data.get("step")
        if isinstance(step, int) and step > 0:
            self._step = step
        chunk = data.get("chunk")
        if not isinstance(chunk, dict):
            return
        kind = str(chunk.get("type") or "")
        if kind == "reasoning-delta":
            text = str(chunk.get("text") or "")
            if text:
                self._sink.emit(
                    ReasoningDelta(step=self._step, text_delta=text, seq=self._next_seq())
                )
            return
        if kind == "text-delta":
            text = str(chunk.get("text") or "")
            if text:
                self._sink.emit(
                    StepTextDelta(
                        step=self._step,
                        text_delta=text,
                        seq=self._next_seq(),
                        channel=StreamChannel.ANSWER.value,
                    )
                )
            return
        if kind == "block-end":
            block = chunk.get("block")
            if isinstance(block, dict) and block.get("type") == "reasoning":
                preview = str(block.get("text") or "")[:200]
                self._sink.emit(ReasoningCompleted(step=self._step, content_preview=preview))

    def _on_tool_call(self, data: _JSON) -> None:
        self._ensure_open()
        call_id = str(data.get("callId") or data.get("id") or f"dsh-{self._next_seq()}")
        name = str(data.get("name") or "")
        arguments = data.get("arguments")
        raw_args = arguments if isinstance(arguments, str) else ""
        projection = project_tool_call(name, raw_args)
        self._open_args[call_id] = (name, raw_args)
        self._sink.emit(
            ToolStarted(
                tool_name=projection.wire_name,
                invocation_id=call_id,
                arguments_preview=raw_args[:1800],
                plugin_state=projection.started_state,
            )
        )

    def _on_tool_result(self, data: _JSON) -> None:
        self._ensure_open()
        call_id = _result_call_id(data)
        stored = self._open_args.pop(call_id, ("", ""))
        name, raw_args = stored
        if not name:
            name = str(data.get("name") or "")
        projection = project_tool_result(name, raw_args, data)
        ok = not bool(projection.invoked_state.get("success") is False)
        self._sink.emit(
            ToolInvoked(
                tool_name=projection.wire_name,
                invocation_id=call_id,
                arguments_preview=raw_args[:1800],
                result_preview=str(
                    projection.invoked_state.get("stdout")
                    or projection.invoked_state.get("content")
                    or ""
                )[:1800],
                ok=ok,
                plugin_state=projection.invoked_state,
            )
        )

    def _on_turn_end(self, data: _JSON) -> None:
        """Record turn status but don't call finish() — caller provides actual output."""
        reason = data.get("reason")
        kind = "completed"
        error = ""
        if isinstance(reason, dict):
            kind = str(reason.get("kind") or "completed")
            failure = reason.get("error") or reason.get("failure")
            if isinstance(failure, dict):
                error = str(failure.get("message") or "")
        self._turn_status = "completed" if kind == "completed" else "failed"
        self._turn_error = error


def _result_call_id(data: _JSON) -> str:
    message = data.get("message")
    if isinstance(message, dict):
        source = message.get("source")
        if isinstance(source, dict) and source.get("callId"):
            return str(source["callId"])
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("toolCallId"):
                    return str(block["toolCallId"])
    return str(data.get("callId") or "")
