"""ToolCall wire-shape TypedDict for the run session writer Protocol.

Mirrors the OpenAI function-calling wire shape (``id`` / ``name`` /
``arguments``). Used as the element type of
:meth:`RunSessionWriterProtocol.append_assistant_message` ``tool_calls``
parameter and as the data payload of ``log/tool_call`` events.
"""

from __future__ import annotations

from typing import TypedDict


class ToolCall(TypedDict):
    """Single tool call in OpenAI wire shape."""

    id: str
    name: str
    arguments: str


__all__ = ["ToolCall"]
