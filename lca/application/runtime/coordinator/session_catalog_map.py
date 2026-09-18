"""Catalog Session facts → EventTranslator input envelopes.

Gateway WS translation uses two tiers:

1. **Catalog facts** (``tool.started.v1``, ``tool.invoked.v1``, …) — durable
   lifecycle SSOT with ``projected_state`` and approval checkpoints.
2. **Spine EPs** (``llm.stream.token``, ``step.tool_call.record``, …) —
   streaming / step-tree observability.

Spine EPs that duplicate catalog lifecycle facts are suppressed here so
``tool_end`` is never published without a preceding ``projected_state`` write.
"""

from __future__ import annotations

from typing import Any

from lca.application.runtime.coordinator.event_translator import wire_tool_call

# Spine execution points superseded by catalog lifecycle facts.
SUPPRESSED_SPINE_EPS = frozenset(
    {
        "body.tool.execute.end",
        "phase.tool.call.start",
        "phase.tool.denied",
    }
)

_TERMINAL_CHECKPOINTS = frozenset({"completed", "failed", "canceled", "cancelled"})


def is_suppressed_spine_ep(execution_point: str | None) -> bool:
    return execution_point in SUPPRESSED_SPINE_EPS


def catalog_session_event_to_stamped(
    event_type: str,
    data: dict[str, Any],
    *,
    assistant_message_id: str | None = None,
) -> dict[str, Any] | None:
    """Map one catalog session event to an EventTranslator envelope, or None."""
    parent = assistant_message_id or None
    handler = _CATALOG_HANDLERS.get(event_type)
    if handler is None:
        return None
    return handler(data, parent=parent)


def _parent_body(body: dict[str, Any], parent: str | None) -> dict[str, Any]:
    if parent:
        body["parentMessageId"] = parent
    return body


def _map_tool_started(data: dict[str, Any], *, parent: str | None) -> dict[str, Any]:
    tool_name = str(data.get("tool_name") or "")
    invocation_id = str(data.get("invocation_id") or "")
    arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
    tool_calling = wire_tool_call(tool_name, invocation_id, arguments)
    return {
        "event": _parent_body(
            {
                "type": "ToolStarted",
                "payload": tool_calling,
            },
            parent,
        )
    }


def _map_tool_invoked(data: dict[str, Any], *, parent: str | None) -> dict[str, Any]:
    tool_name = str(data.get("tool_name") or "")
    invocation_id = str(data.get("invocation_id") or "")
    arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
    tool_calling = wire_tool_call(tool_name, invocation_id, arguments)
    projected = data.get("projected_state")
    if not isinstance(projected, dict):
        projected = {}
    result: dict[str, Any] | None = None
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text:
        result = {"content": output_text}
    elif not data.get("ok", True) and data.get("error"):
        result = {"error": str(data.get("error"))}
    # Fallback: many text-producing tools (``search``, ``web-browsing``, etc.)
    # put their return string on ``obs.payload["text"]`` rather than the
    # ``output`` / ``stdout`` / ``content`` whitelist that
    # ``prepare_tool_invoked`` reads. When the explicit ``output_text`` is
    # empty, surface ``text`` so the LobeHub gateway handler can write the
    # tool return onto the tool message and ``persistAssistantRow`` keeps
    # a non-empty assistant content.
    if result is None and data.get("ok", True):
        text_payload = data.get("text")
        if isinstance(text_payload, str) and text_payload:
            result = {"content": text_payload}
    return {
        "event": _parent_body(
            {
                "type": "ToolInvoked",
                "projected_state": projected,
                "isSuccess": bool(data.get("ok", True)),
                "executionTime": data.get("latency_ms"),
                "result": result,
                "payload": {"toolCalling": tool_calling},
            },
            parent,
        )
    }


def _map_tool_denied(data: dict[str, Any], *, parent: str | None) -> dict[str, Any]:
    tool_name = str(data.get("tool_name") or "")
    return {
        "event": _parent_body(
            {
                "type": "ToolDenied",
                "reason": str(data.get("reason") or "denied"),
                "payload": {"toolCalling": wire_tool_call(tool_name, tool_name, {})},
            },
            parent,
        )
    }


def _map_session_checkpoint(data: dict[str, Any], *, parent: str | None) -> dict[str, Any] | None:
    status = str(data.get("status") or "")
    if status == "waiting_input":
        reason = "waiting_for_human"
        final_status = "waiting_for_human"
    elif status in _TERMINAL_CHECKPOINTS:
        reason = "completed" if status == "completed" else status
        final_status = "done" if status == "completed" else status
    else:
        return None
    del parent
    stamped: dict[str, Any] = {
        "event": {
            "type": "SpineClose",
            "reason": reason,
            "final_state": {"status": final_status},
        }
    }
    pending = data.get("pending_tools_calling")
    if isinstance(pending, list) and pending:
        stamped["event"]["pending_tools_calling"] = pending
    return stamped


def _map_approval_persisted(data: dict[str, Any], *, parent: str | None) -> dict[str, Any] | None:
    """``approval.persisted.v1`` stays journal-internal (recovery SSOT).

    It always pairs with a ``waiting_input`` checkpoint, which already
    yields the WS ``step_start → agent_runtime_end`` pause pair. Mapping
    both would double-publish the pause (run_41571c76b953: four identical
    pairs). Recovery reads the journal fact directly, unaffected.
    """
    del data, parent
    return None


_CATALOG_HANDLERS = {
    "tool.started.v1": _map_tool_started,
    "tool.invoked.v1": _map_tool_invoked,
    "tool.denied.v1": _map_tool_denied,
    "session.checkpoint.v1": _map_session_checkpoint,
    "approval.persisted.v1": _map_approval_persisted,
}


__all__ = (
    "SUPPRESSED_SPINE_EPS",
    "catalog_session_event_to_stamped",
    "is_suppressed_spine_ep",
)
