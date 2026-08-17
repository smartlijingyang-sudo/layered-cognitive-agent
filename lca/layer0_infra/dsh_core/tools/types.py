"""1:1 port of ``@deepseek-ai/dsh-tools/types.ts``.

Durable Tool event vocabulary shared with type-only consumers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NewType

CallId = NewType("CallId", str)
"""Branded call identity."""


@dataclass(frozen=True)
class TextContentBlock:
    """One text content block (the most common variant)."""

    type: str  # "text"
    text: str


@dataclass(frozen=True)
class ImageContentBlock:
    """One image content block."""

    type: str  # "image"
    source: dict[str, Any]


@dataclass(frozen=True)
class ToolUseContentBlock:
    """One tool_use content block."""

    type: str  # "tool_use"
    id: str
    name: str
    input: Any


@dataclass(frozen=True)
class ToolResultContentBlock:
    """One tool_result content block."""

    type: str  # "tool_result"
    tool_use_id: str
    content: Any


ContentBlock = TextContentBlock | ImageContentBlock | ToolUseContentBlock | ToolResultContentBlock
"""One model-facing content block (tagged union by ``type``)."""


@dataclass(frozen=True)
class CodeDispatchStartEventData:
    """Payload recorded when one nested Code Mode Tool dispatch starts."""

    root_call_id: CallId
    parent_call_id: CallId
    sub_call_id: CallId
    name: str
    arguments: Any


@dataclass(frozen=True)
class CodeDispatchEventData:
    """Payload recorded when one nested Code Mode Tool dispatch settles."""

    root_call_id: CallId
    parent_call_id: CallId
    sub_call_id: CallId
    name: str
    arguments: Any
    is_error: bool
    content: list[ContentBlock]
