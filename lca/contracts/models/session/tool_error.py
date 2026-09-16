"""ToolError TypedDict for the run session writer Protocol.

Persisted projection of a tool execution error carried on
``surface/tool_result``. Distinct from the runtime
``EffectReceipt.failure_kind`` classifier tag; this is the journal-side
wire shape.
"""

from __future__ import annotations

from typing import TypedDict


class ToolError(TypedDict, total=False):
    """Structured tool error projection."""

    kind: str
    message: str
    retryable: bool


__all__ = ["ToolError"]
