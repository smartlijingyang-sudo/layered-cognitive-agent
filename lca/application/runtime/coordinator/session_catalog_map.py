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
    return {
        "event": {
            "type": "SpineClose",
            "reason": reason,
            "final_state": {"status": final_status},
        }
    }


def _map_approval_persisted(data: dict[str, Any], *, parent: str | None) -> dict[str, Any] | None:
    """Checkpoint pause — ``approval.persisted.v1`` always pairs with waiting_input."""
    del data, parent
    return {
        "event": {
            "type": "SpineClose",
            "reason": "waiting_for_human",
            "final_state": {"status": "waiting_for_human"},
        }
    }


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
