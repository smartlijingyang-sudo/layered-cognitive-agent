"""Thin compatibility shim over ``gateway.stream_emitter``.

The original ``OpenAISSEProjector`` consumed SSE text frames.
The new ``OpenAIStreamEmitter`` consumes typed ``StampedEvent`` objects.
This module keeps the old ``project_frame(str)`` interface working for
tests and external consumers that haven't migrated yet.
"""

from __future__ import annotations

import json
from typing import Any

from gateway.stream_emitter import (
    OpenAIStreamEmitter,
)
from gateway.stream_emitter import (
    assert_finish_invariant as assert_openai_finish_invariant,  # noqa: F401  — re-exported for tests
)
from lca.layer0_infra.observability.journal.journal_io import record_to_stamped

Chunk = dict[str, Any]


class OpenAISSEProjector(OpenAIStreamEmitter):
    """Backward-compatible wrapper: accepts SSE text frames via ``project_frame``.

    New code should use ``OpenAIStreamEmitter.consume(StampedEvent)`` directly.
    """

    def project_frame(self, frame: str) -> list[dict[str, Any]]:
        """Parse an SSE text frame and project it via the typed emitter."""
        record = _parse_sse_frame(frame)
        if record is None:
            return []
        stamped = record_to_stamped(record)
        if stamped is None:
            return []
        return self.consume(stamped)

    def _emit_finish(self, *_args: Any) -> list[Chunk]:
        """Backward-compat: ignore legacy snapshot argument."""
        return super()._emit_finish()

    @property
    def _snapshot(self) -> None:
        """Backward-compat: legacy attribute, no longer used."""
        return None


def _parse_sse_frame(frame: str) -> dict[str, Any] | None:
    """Extract JSON record from a journal SSE frame."""
    for line in frame.splitlines():
        if line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


def sse_data_lines(chunks: Any) -> Any:
    """Backward-compat: yield SSE data lines from chunks."""

    def _gen() -> Any:
        for chunk in chunks:
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return _gen()


async def stream_openai_from_run(frame_stream: Any, *, chat_id: str, model: str) -> Any:
    """Backward-compat: stream OpenAI SSE from journal frames."""
    from gateway.stream_emitter import stream_openai_chunks

    # The old API took string frames; the new one takes StampedEvents.
    # This shim converts frames to StampedEvents on the fly.
    async def _typed_stream() -> Any:
        async for frame in frame_stream:
            record = _parse_sse_frame(frame)
            if record is None:
                continue
            stamped = record_to_stamped(record)
            if stamped is not None:
                yield stamped

    return stream_openai_chunks(_typed_stream(), chat_id=chat_id, model=model)


async def collect_openai_completion(
    frame_stream: Any, *, chat_id: str, model: str
) -> dict[str, Any]:
    """Backward-compat: collect completion from journal frames."""
    from gateway.stream_emitter import collect_openai_completion as _new_collect

    async def _typed_stream() -> Any:
        async for frame in frame_stream:
            record = _parse_sse_frame(frame)
            if record is None:
                continue
            stamped = record_to_stamped(record)
            if stamped is not None:
                yield stamped

    return await _new_collect(_typed_stream(), chat_id=chat_id, model=model)
