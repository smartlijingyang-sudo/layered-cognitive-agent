"""Named SSE event emitter for LobeHub frontend (fetchSSE protocol).

The LobeHub frontend ``fetchSSE`` routes events by ``ev.event`` name:

    event: text          → content delta (data = JSON string)
    event: reasoning     → thinking delta (data = JSON string)
    event: lca_tool_event→ tool lifecycle (data = JSON object)
    event: usage         → token counts (data = JSON object)

The previous approach embedded tool events inside nameless OpenAI
``chat.completion.chunk`` via ``lca.events`` extension.  ``fetchSSE``
switches on ``ev.event`` with no ``default`` branch, so nameless chunks
are silently dropped — tool cards never render.

This module converts ``JournalOpenAiProjector`` output into properly
named SSE frames, keeping the projector's stateful logic (tool wire
resolution, answer-channel filtering, dedup guards) intact.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


def _sse_named(event: str, data: Any) -> bytes:
    """Format a named SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


async def stream_named_events_from_run(
    frame_stream: AsyncIterator[str],
    *,
    projector: Any,
) -> AsyncIterator[bytes]:
    """Consume journal frames → emit named SSE events for fetchSSE.

    ``projector`` is a ``JournalOpenAiProjector`` instance that converts
    raw journal frames into OpenAI chunks.  We post-process those chunks
    to extract the semantic payload and emit it as a named event.
    """
    async for frame in frame_stream:
        for chunk in projector.project_frame(frame):
            for event in _chunk_to_named_events(chunk):
                yield event

    if not projector._finished:
        for chunk in projector._emit_finish():
            for event in _chunk_to_named_events(chunk):
                yield event

    yield b'event: stop\ndata: "stop"\n\n'


def _chunk_to_named_events(chunk: dict[str, Any]) -> list[bytes]:
    """Convert one OpenAI chunk into zero or more named SSE frames."""
    events: list[bytes] = []

    lca_ext = chunk.get("lca")
    if isinstance(lca_ext, dict):
        for event in lca_ext.get("events") or []:
            events.append(_sse_named("lca_tool_event", event))

    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return events

    delta = choices[0].get("delta") or {}

    reasoning = delta.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        events.append(_sse_named("reasoning", reasoning))

    content = delta.get("content")
    if isinstance(content, str) and content:
        events.append(_sse_named("text", content))

    finish_reason = delta.get("finish_reason") if "delta" in choices[0] else None
    if finish_reason is None:
        finish_reason = choices[0].get("finish_reason")
    if isinstance(finish_reason, str) and finish_reason:
        events.append(_sse_named("stop", finish_reason))

    usage = chunk.get("usage")
    if isinstance(usage, dict) and usage:
        events.append(_sse_named("usage", usage))

    return events
