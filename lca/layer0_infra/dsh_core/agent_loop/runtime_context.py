"""Durable projection state for dynamic runtime context.

1:1 port of ``@deepseek-ai/dsh-agent-loop/runtime-context.ts``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.layer0_infra.dsh_core.session import (
    Session,
    SessionEvent,
    is_replacement_surface_event,
)

SOURCE = "@deepseek-ai/dsh-system-prompt"
CLEARED = (
    "Current runtime context: none. "
    "Earlier runtime-context snapshots no longer apply."
)


@dataclass
class ContextSnapshotSection:
    """One named section of a rendered context snapshot."""

    name: str
    text: str


def _is_owned(message: dict[str, Any]) -> bool:
    src = message.get("source", {})
    return src.get("kind") == "plugin" and src.get("plugin") == SOURCE


def _text_of(message: dict[str, Any]) -> str | None:
    content = message.get("content", [])
    if len(content) == 1 and content[0].get("type") == "text":
        return content[0].get("text")
    return None


class RuntimeContextProjection:
    """Tracks the last retained runtime-context snapshot."""

    def __init__(self, ctx: Any, session: Session) -> None:
        self._retained: dict[str, Any] | object | None = _UNSET
        self._session = session

        surface = set(session.surface.nodes) if hasattr(session, "surface") else set()
        for event in reversed(session.events):
            if event.type != "user/message" or not _is_owned(event.data):
                continue
            if self._retained is _UNSET:
                self._retained = None
            if event.seq in surface:
                self._retained = {"seq": event.seq, "text": _text_of(event.data)}
                break

        def on_session_event(subject: Any, event: SessionEvent) -> None:
            if subject is not session:
                return
            if event.type == "user/message" and _is_owned(event.data):
                self._retained = {"seq": event.seq, "text": _text_of(event.data)}
            elif (
                self._retained is not None
                and self._retained is not _UNSET
                and is_replacement_surface_event(event)
                and event.source_event_seqs is not None
                and self._retained["seq"] in event.source_event_seqs
            ):
                self._retained = None

        ctx.on("session/event", on_session_event)

    def project(
        self,
        current: str,
        sections: list[ContextSnapshotSection],
    ) -> dict[str, Any] | None:
        """Create an uncommitted snapshot only when the retained value differs."""
        if self._retained is _UNSET and len(current) == 0:
            return None
        snapshot = CLEARED if len(current) == 0 else current
        if isinstance(self._retained, dict) and self._retained.get("text") == snapshot:
            return None
        source: dict[str, Any]
        if len(sections) == 0:
            source = {"kind": "plugin", "plugin": SOURCE}
        else:
            source = {
                "kind": "plugin",
                "plugin": SOURCE,
                "form": "snapshot",
                "sections": [{"name": s.name, "text": s.text} for s in sections],
            }
        return {
            "content": [{"type": "text", "text": snapshot}],
            "source": source,
        }


class _Unset:
    """Sentinel for 'no snapshot ever existed'."""


_UNSET = _Unset()
