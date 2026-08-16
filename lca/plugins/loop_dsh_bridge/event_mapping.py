"""DSH → SessionEvent mapping (spec §D.2).

Translates DSH runtime notifications into the LCA session event vocabulary
so the harness spine can treat DSH the same as any other loop provider.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import structlog

from lca.contracts.harness.session import SessionEvent

_log = structlog.get_logger(__name__)

# DSH notification type → LCA session event type (spec §D.2).
# The core six (turn/start, turn/end, tool/call, tool/result,
# user/message, assistant/message) are required; the remainder round
# out the DSH surface the harness cares about.
DSH_EVENT_MAP: dict[str, str] = {
    "agent/created": "session.created.v1",
    "turn/start": "turn.started.v1",
    "turn/end": "turn.ended.v1",
    "step/start": "step.started.v1",
    "step/end": "step.ended.v1",
    "user/message": "message.accepted.v1",
    "assistant/message": "model.completed.v1",
    "request/header": "model.requested.v1",
    "assistant/chunk": "model.completed.v1",
    "tool/call": "tool.called.v1",
    "tool/result": "tool.completed.v1",
}


@dataclass(frozen=True)
class MappedEvent:
    """Result of mapping a DSH notification to a SessionEvent payload."""

    type: str
    data: dict[str, Any]
    actor: str | None = None


class DshEventMapper:
    """Stateful mapper: tracks turn/step counters across one DSH session."""

    def __init__(self, *, session_id: str, provider: str = "lca.loop.dsh_bridge") -> None:
        self._session_id = session_id
        self._provider = provider
        self._seq = 0
        self._turn = 0
        self._step = 0

    def map_notification(self, event_type: str, data: dict[str, Any]) -> MappedEvent | None:
        lca_type = DSH_EVENT_MAP.get(event_type)
        if lca_type is None:
            return None
        handler = getattr(self, f"_handle_{_safe_name(event_type)}", None)
        if handler is not None:
            return handler(data, lca_type)
        return MappedEvent(type=lca_type, data=dict(data))

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _handle_turn_start(self, data: dict[str, Any], lca_type: str) -> MappedEvent:
        self._turn += 1
        return MappedEvent(type=lca_type, data={"turn": self._turn})

    def _handle_turn_end(self, data: dict[str, Any], lca_type: str) -> MappedEvent:
        reason = "completed"
        reason_obj = data.get("reason")
        if isinstance(reason_obj, dict):
            kind = str(reason_obj.get("kind") or "completed")
            reason = "error" if kind != "completed" else "completed"
        return MappedEvent(
            type=lca_type,
            data={"turn": self._turn, "reason": reason},
        )

    def _handle_step_start(self, data: dict[str, Any], lca_type: str) -> MappedEvent:
        step = data.get("step")
        if isinstance(step, int) and step > 0:
            self._step = step
        else:
            self._step += 1
        return MappedEvent(type=lca_type, data={"turn": self._turn, "step": self._step})

    def _handle_request_header(self, data: dict[str, Any], lca_type: str) -> MappedEvent:
        return MappedEvent(
            type=lca_type,
            data={
                "turn": self._turn,
                "step": self._step,
                "provider": self._provider,
                "model": str(data.get("model") or "dsh"),
            },
            actor="tool:dsh",
        )

    def _handle_assistant_chunk(self, data: dict[str, Any], lca_type: str) -> MappedEvent:
        chunk = data.get("chunk")
        if not isinstance(chunk, dict):
            return MappedEvent(type=lca_type, data={"turn": self._turn, "step": self._step})
        kind = str(chunk.get("type") or "")
        text = str(chunk.get("text") or "")
        return MappedEvent(
            type=lca_type,
            data={
                "turn": self._turn,
                "step": self._step,
                "chunk_kind": kind,
                "text": text,
            },
            actor="agent",
        )

    def _handle_tool_call(self, data: dict[str, Any], lca_type: str) -> MappedEvent:
        call_id = str(data.get("callId") or data.get("id") or f"dsh-{self._seq + 1}")
        name = str(data.get("name") or "")
        arguments = data.get("arguments")
        raw_args = arguments if isinstance(arguments, str) else ""
        return MappedEvent(
            type=lca_type,
            data={
                "call_id": call_id,
                "tool_name": name,
                "arguments_ref": raw_args[:1800],
            },
            actor=f"tool:{name}",
        )

    def _handle_tool_result(self, data: dict[str, Any], lca_type: str) -> MappedEvent:
        call_id = str(data.get("callId") or "")
        if not call_id:
            msg = data.get("message")
            if isinstance(msg, dict):
                src = msg.get("source")
                if isinstance(src, dict) and src.get("callId"):
                    call_id = str(src["callId"])
        return MappedEvent(
            type=lca_type,
            data={
                "call_id": call_id,
                "success": True,
                "result_ref": str(data.get("output") or "")[:1800],
            },
        )


def to_session_event(
    mapped: MappedEvent,
    *,
    session_id: str,
    provider: str = "lca.loop.dsh_bridge",
) -> SessionEvent:
    """Convert a MappedEvent to a full SessionEvent with timestamp and scope."""
    return SessionEvent(
        type=mapped.type,
        seq=0,  # caller assigns real seq via SessionStore
        time=int(time.time() * 1000),
        data=mapped.data,
        session_id=session_id,
        actor=mapped.actor,
        provider=provider,
    )


def _safe_name(event_type: str) -> str:
    """Convert 'turn/start' → 'turn_start' for method lookup."""
    return event_type.replace("/", "_").replace(".", "_")


class DshJournalProjector:
    """Stateless projector: converts a DSH notification event to a MappedEvent.

    Unlike :class:`DshEventMapper` (which tracks turn/step counters across
    a session), this projector is pure per-event: suitable for journaling,
    replay, and harness spine tests that feed events without ordering.

    Unknown DSH event types return ``None`` and emit a warning log.
    """

    def project(self, dsh_event: Any) -> MappedEvent | None:
        """Map a DSH event (duck-typed: needs ``.type`` and optional ``.data``)
        to a :class:`MappedEvent`, or ``None`` if the event type is unknown."""
        event_type = getattr(dsh_event, "type", None)
        if event_type is None:
            _log.warning("dsh_event_missing_type", dsh_event_repr=repr(dsh_event))
            return None

        lca_type = DSH_EVENT_MAP.get(event_type)
        if lca_type is None:
            _log.warning(
                "dsh_unknown_event",
                dsh_type=event_type,
            )
            return None

        data = getattr(dsh_event, "data", None)
        if data is None or not isinstance(data, dict):
            data = {}

        return MappedEvent(type=lca_type, data=dict(data))
