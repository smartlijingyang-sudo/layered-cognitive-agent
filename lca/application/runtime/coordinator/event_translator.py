"""StampedEvent → AgentStreamEvent.data fold.

Pure function table. Each fold row mirrors the translation table in
spec §5.3. `tool_end.data` deliberately omits `projected_state` — the
server-side coordinator writes the full `projected_state` into the
tool message's `pluginState` DB column BEFORE publishing the event;
the front-end `gatewayEventHandler.tool_end` then `fetchAndReplaceMessages`
reads the populated row. See spec §5.3.1.
"""

from __future__ import annotations

from typing import Any


def _text_delta(e: dict[str, Any]) -> str:
    for key in ("text_delta", "delta", "content"):
        raw = e.get(key)
        if isinstance(raw, str) and raw:
            return raw
    return ""


def _inner_payload(e: dict[str, Any]) -> dict[str, Any]:
    nested = e.get("payload")
    if isinstance(nested, dict):
        return nested
    return e


def wire_tool_call(
    tool_name: str,
    invocation_id: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from lca.plugins.transport.webserver.wire.wire import resolve

    coords = resolve(tool_name)
    if coords is None:
        identifier, api_name = "lobe-cloud-sandbox", tool_name
    else:
        identifier, api_name = coords
    return {
        "id": invocation_id or tool_name,
        "identifier": identifier,
        "apiName": api_name,
        "arguments": dict(arguments or {}),
        "type": "builtin",
    }


class EventTranslator:
    """Pure fold from a StampedEvent to an AgentStreamEvent payload."""

    def translate(self, stamped: dict) -> dict | None:
        """Return the AgentStreamEvent envelope (type + data) or None to ignore."""
        event = stamped.get("event") or {}
        kind = event.get("kind")
        if kind == "ignore":
            return None

        execution_point = event.get("execution_point")
        if isinstance(execution_point, str):
            spine_handler = _SPINE_HANDLERS.get(execution_point)
            if spine_handler is not None:
                return spine_handler(event)

        etype = event.get("type")
        handler = _HANDLERS.get(etype)
        if handler is None:
            return None
        return handler(event)

    # ── Translation rules (one per spec §5.3 row) ────────────────────

    @staticmethod
    def _llm_call_started(e: dict) -> dict:
        return {
            "type": "stream_start",
            "data": {"assistantMessage": e.get("assistantMessage", {})},
        }

    @staticmethod
    def _text_delta_event(e: dict) -> dict | None:
        delta = _text_delta(e)
        if not delta:
            return None
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "text",
                "content": delta,
                "snapshotMode": "append",
            },
        }

    @staticmethod
    def _step_text_delta(e: dict) -> dict | None:
        channel = e.get("channel", "decision")
        if channel not in ("answer", "all"):
            return None
        return EventTranslator._text_delta_event(e)

    @staticmethod
    def _reasoning_delta(e: dict) -> dict | None:
        delta = _text_delta(e)
        if not delta:
            return None
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "reasoning",
                "reasoning": delta,
                "snapshotMode": "append",
            },
        }

    @staticmethod
    def _assistant_responded(e: dict) -> dict | None:
        content = str(e.get("content") or "")
        if not content:
            return None
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "text",
                "content": content,
                "snapshotMode": "append",
            },
        }

    @staticmethod
    def _decision_made(e: dict) -> dict:
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "tools_calling",
                "toolsCalling": e.get("tool_calls", []),
            },
        }

    @staticmethod
    def _tool_started(e: dict) -> dict:
        payload = e.get("payload") or e.get("toolCalling") or {}
        if not payload and e.get("tool_name"):
            payload = wire_tool_call(
                str(e.get("tool_name") or ""),
                str(e.get("invocation_id") or ""),
                e.get("arguments") if isinstance(e.get("arguments"), dict) else {},
            )
        return {
            "type": "tool_start",
            "data": {
                "parentMessageId": e.get("parentMessageId"),
                "toolCalling": payload,
            },
        }

    @staticmethod
    def _tool_invoked(e: dict) -> dict:
        """spec §5.3.1: NO top-level projected_state — use ``result.state`` (native shape)."""
        result_raw = e.get("result")
        result: dict[str, Any] = dict(result_raw) if isinstance(result_raw, dict) else {}
        projected = e.get("projected_state")
        if isinstance(projected, dict) and projected:
            result["state"] = projected
        return {
            "type": "tool_end",
            "data": {
                "isSuccess": e.get("isSuccess", True),
                "result": result or None,
                "payload": e.get("payload"),
                "executionTime": e.get("executionTime"),
            },
        }

    @staticmethod
    def _tool_denied(e: dict) -> dict:
        return {
            "type": "tool_end",
            "data": {
                "isSuccess": False,
                "result": {"error": e.get("reason", "denied")},
            },
        }

    @staticmethod
    def _step_start(e: dict) -> dict:
        return {
            "type": "step_start",
            "data": {
                "phase": e.get("phase"),
                "requiresApproval": e.get("requiresApproval"),
                "pendingToolsCalling": e.get("pendingToolsCalling"),
            },
        }

    @staticmethod
    def _step_finished(e: dict) -> dict:
        return {
            "type": "stream_end",
            "data": {
                "finalContent": e.get("finalContent"),
            },
        }

    @staticmethod
    def _spine_close(e: dict) -> dict:
        final_state = e.get("final_state") or {}
        status = final_state.get("status", "done")
        return {
            "type": "agent_runtime_end",
            "data": {
                "finalState": final_state,
                "reason": e.get("reason", status),
                "reasonDetail": e.get("reasonDetail", ""),
                "phase": "execution_complete",
            },
        }

    @staticmethod
    def _llm_error(e: dict) -> dict:
        return {
            "type": "error",
            "data": {
                "type": e.get("errorType"),
                "message": e.get("message"),
                "body": e.get("body"),
                "provider": e.get("provider"),
            },
        }

    @staticmethod
    def _llm_retry(e: dict) -> dict:
        return {
            "type": "stream_retry",
            "data": {
                "attempt": e.get("attempt", 1),
                "max": e.get("max", 3),
                "provider": e.get("provider"),
                "delayMs": e.get("delayMs"),
            },
        }

    @staticmethod
    def _agent_intervention_request(e: dict) -> dict:
        return {
            "type": "agent_intervention_request",
            "data": {
                "apiName": e.get("apiName"),
                "identifier": e.get("identifier"),
                "arguments": e.get("arguments", {}),
                "toolCallId": e.get("toolCallId"),
                "deadline": e.get("deadline", 0),
            },
        }

    # ── Session spine EP → gateway (ADR-0194 SSOT) ─────────────────

    @staticmethod
    def _spine_llm_call_start(e: dict) -> dict:
        parent = e.get("parentMessageId")
        assistant: dict[str, Any] = {}
        if isinstance(parent, str) and parent:
            assistant["id"] = parent
        return {
            "type": "stream_start",
            "data": {"assistantMessage": assistant},
        }

    @staticmethod
    def _spine_llm_stream_token(e: dict) -> dict | None:
        payload = _inner_payload(e)
        delta = str(payload.get("text_delta") or "")
        if not delta:
            return None
        kind = payload.get("channel_kind") or "output"
        if kind == "reasoning":
            return {
                "type": "stream_chunk",
                "data": {
                    "chunkType": "reasoning",
                    "reasoning": delta,
                    "snapshotMode": "append",
                },
            }
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "text",
                "content": delta,
                "snapshotMode": "append",
            },
        }

    @staticmethod
    def _spine_llm_header_assistant(e: dict) -> dict | None:
        payload = _inner_payload(e)
        content = str(payload.get("assistant_content") or "")
        if not content:
            return None
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "text",
                "content": content,
                "snapshotMode": "append",
            },
        }

    @staticmethod
    def _spine_tool_call_record(e: dict) -> dict | None:
        payload = _inner_payload(e)
        tool_name = str(payload.get("tool_name") or "")
        invocation_id = str(payload.get("invocation_id") or payload.get("tool_call_id") or "")
        if not tool_name or not invocation_id:
            return None
        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "tools_calling",
                "toolsCalling": [wire_tool_call(tool_name, invocation_id, arguments)],
            },
        }

    @staticmethod
    def _spine_phase_tool_start(e: dict) -> dict | None:
        payload = _inner_payload(e)
        tool_name = str(payload.get("tool_name") or "")
        invocation_id = str(payload.get("invocation_id") or "")
        if not tool_name:
            return None
        tool_calling = wire_tool_call(tool_name, invocation_id, {})
        return {
            "type": "tool_start",
            "data": {
                "parentMessageId": e.get("parentMessageId"),
                "toolCalling": tool_calling,
            },
        }

    @staticmethod
    def _spine_body_tool_end(e: dict) -> dict | None:
        payload = _inner_payload(e)
        invocation_id = str(payload.get("invocation_id") or "")
        tool_name = str(payload.get("tool_name") or "")
        outcome = str(payload.get("outcome") or "")
        ok = payload.get("ok")
        is_success = ok if isinstance(ok, bool) else outcome not in ("failure", "failed", "error")
        tool_calling = wire_tool_call(tool_name, invocation_id, {})
        output_text = payload.get("output_text")
        result: dict[str, Any] | None = None
        if isinstance(output_text, str) and output_text:
            result = {"content": output_text}
        return {
            "type": "tool_end",
            "data": {
                "isSuccess": is_success,
                "executionTime": payload.get("latency_ms"),
                "result": result,
                "payload": {
                    "parentMessageId": e.get("parentMessageId"),
                    "toolCalling": tool_calling,
                },
            },
        }

    @staticmethod
    def _spine_kernel_run_stop(e: dict) -> dict:
        payload = _inner_payload(e)
        final_state = {"status": payload.get("status") or "completed"}
        return {
            "type": "agent_runtime_end",
            "data": {
                "finalState": final_state,
                "reason": "completed",
                "reasonDetail": str(payload.get("error") or ""),
                "phase": "execution_complete",
            },
        }


_HANDLERS = {
    "LlmCallStarted": EventTranslator._llm_call_started,
    "LlmCallTextDelta": EventTranslator._text_delta_event,
    "StepTextDelta": EventTranslator._step_text_delta,
    "ReasoningDelta": EventTranslator._reasoning_delta,
    "assistant.responded.v1": EventTranslator._assistant_responded,
    "DecisionMade": EventTranslator._decision_made,
    "ToolStarted": EventTranslator._tool_started,
    "ToolInvoked": EventTranslator._tool_invoked,
    "ToolDenied": EventTranslator._tool_denied,
    "StepStart": EventTranslator._step_start,
    "StepFinished": EventTranslator._step_finished,
    "SpineClose": EventTranslator._spine_close,
    "LlmError": EventTranslator._llm_error,
    "LlmRetry": EventTranslator._llm_retry,
    "AgentInterventionRequest": EventTranslator._agent_intervention_request,
}

_SPINE_HANDLERS = {
    "llm.call.start": EventTranslator._spine_llm_call_start,
    "llm.stream.token": EventTranslator._spine_llm_stream_token,
    "llm.request.header.assistant": EventTranslator._spine_llm_header_assistant,
    "step.tool_call.record": EventTranslator._spine_tool_call_record,
    "phase.tool.call.start": EventTranslator._spine_phase_tool_start,
    "body.tool.execute.end": EventTranslator._spine_body_tool_end,
    "kernel.run.stop": EventTranslator._spine_kernel_run_stop,
}


__all__ = ("EventTranslator", "wire_tool_call")
