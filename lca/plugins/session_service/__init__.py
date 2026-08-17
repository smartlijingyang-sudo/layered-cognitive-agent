"""Session service plugin — event sourcing, surface projection, derive_messages."""

from __future__ import annotations

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.session.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("session_service",),
)

name = "lca.session.service"
provides = "session_service"

# --- Surface event mapping (DSH-aligned) ---
# Surface events are those whose data projects directly into LLM-visible messages.
# Non-surface events (turn.started, step.started, model.completed, etc.) are skipped.

_SURFACE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "message.accepted.v1",
        "assistant.responded.v1",
        "tool.completed.v1",
    }
)


def _project_message_accepted(data: dict[str, Any]) -> dict[str, Any] | None:
    if data.get("role") != "user":
        return None
    return {"role": "user", "content": data.get("content_ref", "")}


def _project_assistant_responded(data: dict[str, Any]) -> dict[str, Any] | None:
    return {"role": "assistant", "content": data.get("content", "")}


def _project_tool_completed(data: dict[str, Any]) -> dict[str, Any] | None:
    return {
        "role": "tool",
        "content": data.get("result_ref", ""),
        "tool_call_id": data.get("call_id", ""),
    }


_SURFACE_PROJECTORS: dict[str, Any] = {
    "message.accepted.v1": _project_message_accepted,
    "assistant.responded.v1": _project_assistant_responded,
    "tool.completed.v1": _project_tool_completed,
}


class SessionService:
    """Event-sourced session management and LLM message projection.

    Pure functions — no I/O side effects. The service wraps SessionStore
    creation and provides derive_messages() for projecting session events
    into the message dicts consumed by LLM adapters.
    """

    def create_session(self, header: Any) -> Any:
        """Create a new SessionStore for the given header."""
        from lca.harness.session.store import SessionStore

        return SessionStore(header)

    def derive_messages(self, events: list[Any]) -> list[dict[str, Any]]:
        """Project a list of SessionEvent objects into LLM-visible message dicts.

        Non-surface events are silently skipped.
        """
        messages: list[dict[str, Any]] = []
        for event in events:
            event_type = event.type if hasattr(event, "type") else getattr(event, "type", None)
            if event_type is None or event_type not in _SURFACE_EVENT_TYPES:
                continue
            msg = self.derive_event_message(event_type, event.data)
            if msg is not None:
                messages.append(msg)
        return messages

    def is_surface_event(self, event_type: str) -> bool:
        """Return True if *event_type* produces an LLM-visible message."""
        return event_type in _SURFACE_EVENT_TYPES

    def derive_event_message(self, event_type: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Project a single event's data into a message dict, or None."""
        projector = _SURFACE_PROJECTORS.get(event_type)
        if projector is None:
            return None
        return projector(data)


def apply(ctx: Any, config: Any) -> None:
    service = SessionService()
    ctx.mount("session_service", service)
