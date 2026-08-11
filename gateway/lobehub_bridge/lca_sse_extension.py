"""LCA extension payload on OpenAI chat.completion.chunk (LobeHub G2A).

Mode A (closed-loop): the full tool lifecycle is projected via ``lca.events``
only — never ``delta.tool_calls`` (which would trigger LobeHub's client-side
``call_tool → call_llm`` loop and duplicate LCA runs).

Event types:
- ``tool_started`` — UI card + wire metadata (server-executed)
- ``tool_result`` / ``tool_state`` — result merge + live sandbox stdout
- ``run_error`` — terminal run failure surfaced to the stream consumer
"""

from __future__ import annotations

from typing import Any, Literal

LCA_SSE_EXTENSION_VERSION = 1

LcaToolEventType = Literal["tool_started", "tool_result", "tool_state", "run_error"]
LCA_CLOSED_LOOP_MARKER = True


def lca_tool_started_event(
    *,
    tool_call_id: str,
    wire_name: str,
    identifier: str,
    api_name: str,
    arguments: str,
    lca_tool_name: str = "",
) -> dict[str, Any]:
    """Announce a server-side tool invocation (Mode A — no OpenAI tool_calls delta)."""
    event: dict[str, Any] = {
        "type": "tool_started",
        "tool_call_id": tool_call_id,
        "wire_name": wire_name,
        "identifier": identifier,
        "api_name": api_name,
        "arguments": arguments,
        "closed_loop": LCA_CLOSED_LOOP_MARKER,
    }
    if lca_tool_name:
        event["lca_tool_name"] = lca_tool_name
    return event


def lca_run_error_event(*, message: str, code: str = "lca_run_failed") -> dict[str, Any]:
    return {
        "type": "run_error",
        "message": message,
        "code": code,
        "closed_loop": LCA_CLOSED_LOOP_MARKER,
    }


def lca_tool_result_event(
    *,
    tool_call_id: str,
    content: str,
    state: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "tool_result",
        "tool_call_id": tool_call_id,
        "content": content,
    }
    if state:
        event["state"] = state
    if error:
        event["error"] = error
    return event


def lca_tool_state_event(
    *,
    tool_call_id: str,
    state: dict[str, Any],
    snapshot_seq: int,
) -> dict[str, Any]:
    return {
        "type": "tool_state",
        "tool_call_id": tool_call_id,
        "state": state,
        "snapshot_seq": snapshot_seq,
    }


def merge_lca_extension(body: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return body
    existing = body.get("lca")
    merged_events: list[dict[str, Any]] = []
    if isinstance(existing, dict) and isinstance(existing.get("events"), list):
        merged_events.extend(existing["events"])
    merged_events.extend(events)
    return {
        **body,
        "lca": {"v": LCA_SSE_EXTENSION_VERSION, "events": merged_events},
    }
