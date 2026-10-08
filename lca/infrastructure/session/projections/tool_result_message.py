"""OpenAI-shaped wire message builders for model-visible tool results (ADR-0201).

Payload-to-text extraction for tool Observations has exactly one owner:
:func:`lca.cognition.body.emit.observation_surface.observation_content`,
the seam shared by ``SimpleBody.dispatch_tool_call`` and
``effect.execute``. A second extractor lived here before and drifted; it
was deleted together with its clip helper because no caller remained.
This module only builds the wire envelope and renders ToolError dicts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def tool_error_text(error: Mapping[str, Any] | None) -> str:
    """Render a ToolError dict into model-visible text.

    Shared projection so ``derive_event_message`` and ``_tool_result_content``
    show the same failure text. A failed tool call must surface its error
    even when the raw content is empty or carries only a source marker;
    otherwise the model sees an empty success and blindly retries
    (run_f70ccf932e9d: 24 ``send_message`` re-asks on a deferred-namespace
    block that never reached the model).
    """
    if not error:
        return ""
    kind = str(error.get("kind") or "execution")
    message = str(error.get("message") or "").strip() or "unknown error"
    retryable = bool(error.get("retryable"))
    return f"[tool_error kind={kind} retryable={retryable}] {message}"


def build_openai_tool_result_message(
    *,
    tool_call_id: str,
    content: str,
    error: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Wire message dict consumed by ``derive_event_message`` and OpenAI history."""
    call_id = tool_call_id.strip()
    err_text = tool_error_text(error)
    text = f"{content}\n{err_text}" if content and err_text else (err_text or content)
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": text,
    }


__all__ = [
    "build_openai_tool_result_message",
    "tool_error_text",
]
