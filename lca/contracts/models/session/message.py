"""Message wire-shape TypedDict for the run session writer Protocol.

The output of :meth:`RunSessionWriterProtocol.derive_messages` — the
OpenAI-compatible message list the model sees on the next dispatch.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class ToolCallRef(TypedDict):
    """Tool call ref carried inside assistant messages."""

    id: str
    name: str
    arguments: str


class Message(TypedDict, total=False):
    """One wire-shape message. ``role`` is always present."""

    role: str
    content: str | None
    tool_calls: NotRequired[list[ToolCallRef] | None]
    tool_call_id: NotRequired[str | None]


__all__ = ["Message", "ToolCallRef"]
