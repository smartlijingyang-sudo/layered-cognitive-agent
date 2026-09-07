"""Append model-visible surface events to the bound Session (ADR-0191 Wave A2)."""

from __future__ import annotations

from typing import Any

from lca.loop.fact_gateway import append_surface_bound
from lca_kernel.events.fold.fold import SURFACE_USER_TYPE

_SURFACE_ACTOR = "surface"


def append_human_answer_surface(
    text: str,
    *,
    source: str = "human_answer",
    tool_name: str = "askUserQuestion",
    session: object | None = None,
) -> None:
    """Record a resumed HIL answer as durable user surface for derive_messages."""
    content = text.strip()
    if not content:
        return
    append_surface_bound(
        SURFACE_USER_TYPE,
        {
            "content": content,
            "messages": [{"role": "user", "content": content}],
            "source": {"kind": "plugin", "plugin_id": source, "reason": tool_name},
        },
        actor=_SURFACE_ACTOR,
        surface_op="append",
        visibility="model",
        session=session,
    )


def append_user_surface(
    message: dict[str, Any],
    *,
    session: object | None = None,
) -> None:
    """Append a provider-style user message dict to the surface log."""
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return
    append_surface_bound(
        SURFACE_USER_TYPE,
        {"content": content, "messages": [dict(message)]},
        actor=_SURFACE_ACTOR,
        surface_op="append",
        visibility="model",
        session=session,
    )


__all__ = ["append_human_answer_surface", "append_user_surface"]
