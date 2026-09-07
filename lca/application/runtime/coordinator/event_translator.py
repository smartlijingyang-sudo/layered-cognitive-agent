"""StampedEvent → AgentStreamEvent.data fold.

Pure function table. Each fold row mirrors the translation table in
spec §5.3. `tool_end.data` deliberately omits `projected_state` — the
server-side coordinator writes the full `projected_state` into the
tool message's `pluginState` DB column BEFORE publishing the event;
the front-end `gatewayEventHandler.tool_end` then `fetchAndReplaceMessages`
reads the populated row. See spec §5.3.1.
"""

from __future__ import annotations


class EventTranslator:
    """Pure fold from a StampedEvent to an AgentStreamEvent payload."""

    def translate(self, stamped: dict) -> dict | None:
        """Return the AgentStreamEvent envelope (type + data) or None to ignore."""
        event = stamped.get("event") or {}
        kind = event.get("kind")
        if kind == "ignore":
            return None
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
    def _text_delta(e: dict) -> dict:
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "text",
                "content": e.get("delta", ""),
                "snapshotMode": "append",
            },
        }

    @staticmethod
    def _reasoning_delta(e: dict) -> dict:
        return {
            "type": "stream_chunk",
            "data": {
                "chunkType": "reasoning",
                "content": e.get("delta", ""),
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
        payload = e.get("payload") or {}
        return {
            "type": "tool_start",
            "data": {
                "parentMessageId": e.get("parentMessageId"),
                "toolCalling": payload,
            },
        }

    @staticmethod
    def _tool_invoked(e: dict) -> dict:
        """spec §5.3.1: NO projected_state in the WS event — server writes it to DB."""
        return {
            "type": "tool_end",
            "data": {
                "isSuccess": e.get("isSuccess", True),
                "result": e.get("result"),
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


_HANDLERS = {
    "LlmCallStarted": EventTranslator._llm_call_started,
    "LlmCallTextDelta": EventTranslator._text_delta,
    "ReasoningDelta": EventTranslator._reasoning_delta,
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


__all__ = ("EventTranslator",)
