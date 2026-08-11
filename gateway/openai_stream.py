"""Async streaming adapters — journal SSE frames → OpenAI chat.completion SSE.

These functions bridge the LCA journal event stream to the standard
OpenAI ``chat.completion.chunk`` SSE protocol expected by LobeHub.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

from gateway.openai_projector import JournalOpenAiProjector


def sse_data_lines(chunks: Iterator[dict[str, Any]]) -> Iterator[bytes]:
    """Yield ``data: {json}\\n\\n`` bytes for each chunk, ending with ``[DONE]``."""
    for chunk in chunks:
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode()
    yield b"data: [DONE]\n\n"


async def stream_openai_from_run(
    frame_stream: AsyncIterator[str],
    *,
    chat_id: str,
    model: str,
) -> AsyncIterator[bytes]:
    """Stream standard OpenAI SSE chunks for LobeHub model-runtime.

    Each frame is a nameless ``data: {chat.completion.chunk}`` line with
    optional ``lca`` extension for tool events.  The LobeHub backend's
    OpenAI SDK parses these into ``ChatCompletionChunk`` objects; the
    patched ``transformQwenStream`` / ``transformOpenAIStream`` extracts
    ``lca.events`` for tool-card rendering.
    """
    projector = JournalOpenAiProjector(chat_id=chat_id, model=model)
    async for frame in frame_stream:
        for chunk in projector.project_frame(frame):
            yield b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"
    if not projector._finished:
        for chunk in projector._emit_finish():
            yield b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + b"\n\n"
    yield b"data: [DONE]\n\n"


async def collect_openai_completion(
    frame_stream: AsyncIterator[str],
    *,
    chat_id: str,
    model: str,
) -> dict[str, Any]:
    """Collect all SSE frames into a single non-streaming chat.completion response."""
    projector = JournalOpenAiProjector(chat_id=chat_id, model=model)
    parts: list[str] = []
    async for frame in frame_stream:
        for chunk in projector.project_frame(frame):
            delta = chunk["choices"][0].get("delta") or {}
            text = delta.get("content")
            if isinstance(text, str) and text:
                parts.append(text)
    if not projector._finished:
        projector._emit_finish()
    return projector.completion_json("".join(parts))
