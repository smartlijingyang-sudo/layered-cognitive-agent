"""Append model-visible surface events to the bound Session (ADR-0191 Wave A2)."""

from __future__ import annotations

from typing import Any, Protocol


class _SurfaceSession(Protocol):
    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        surface_op: str,
        visibility: str,
    ) -> object: ...
from lca_kernel.events.fold.fold import SURFACE_USER_TYPE


def append_human_answer_surface(
    session: _SurfaceSession,
    text: str,
    *,
    source: str = "human_answer",
    tool_name: str = "askUserQuestion",
) -> None:
    """Record a resumed HIL answer as durable user surface for derive_messages."""
    content = text.strip()
    if not content:
        return
    session.append(
        SURFACE_USER_TYPE,
        {
            "content": content,
            "messages": [{"role": "user", "content": content}],
            "source": {"kind": "plugin", "plugin_id": source, "reason": tool_name},
        },
        surface_op="append",
        visibility="model",
    )


def append_user_surface(session: _SurfaceSession, message: dict[str, Any]) -> None:
    """Append a provider-style user message dict to the surface log."""
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return
    session.append(
        SURFACE_USER_TYPE,
        {"content": content, "messages": [dict(message)]},
        surface_op="append",
        visibility="model",
    )


__all__ = ["append_human_answer_surface", "append_user_surface"]
