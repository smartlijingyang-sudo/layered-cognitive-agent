"""Run live SSE streams — fold-only read path (ADR-0195 §2.4 P3-09)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from lca.infrastructure.observability.journal.stream.live_tail import (
    TEXT_CHANNEL_ALL,
    LiveGap,
    iter_live_sse,
)
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession


class _StampedShim:
    """Adapter so ``OpenAIStreamEncoder`` can dispatch on dict-backed stamps."""

    def __init__(self, stamped: Any) -> None:
        self._stamped = stamped

    def __getattr__(self, name: str) -> Any:
        data = getattr(self._stamped, "data", None) or {}
        if isinstance(data, dict) and name in data:
            return data[name]
        return getattr(self._stamped, name, "")


async def stream_chat_completion(
    session: RunSession,
    *,
    last_seq: int = 0,
) -> AsyncIterator[bytes]:
    """Stream a run's journal events encoded as OpenAI ChatCompletion chunks."""
    from lca.plugins.transport.openai_stream_encoder__chunk_provider import (
        OpenAIChatChunkBuilder,
    )
    from lca.plugins.transport.openai_stream_encoder__encoder_provider import (
        OpenAIStreamEncoder,
    )

    builder = OpenAIChatChunkBuilder(model="solo")
    encoder = OpenAIStreamEncoder()

    async def _journal_stream() -> AsyncIterator[Any]:
        try:
            async for stamped in session.tail.subscribe(after_seq=last_seq):
                if isinstance(stamped, LiveGap):
                    continue
                inner = getattr(stamped, "event", None)
                if inner is None:
                    inner = _StampedShim(stamped)
                yield inner
        except asyncio.CancelledError:
            return

    try:
        async for line in encoder.encode(_journal_stream(), chunk_builder=builder):
            yield line
            if line == builder.done():
                return
    finally:
        if hasattr(session.tail, "_subscribers"):
            subscribers = getattr(session.tail, "_subscribers", ())
            for sub in list(subscribers):
                with contextlib.suppress(Exception):
                    sub.queue.put_nowait(None)


async def iter_stamped_events(
    session: RunSession,
    *,
    after_seq: int = 0,
) -> AsyncIterator[Any]:
    """Yield the raw ``StampedEvent`` stream for one run."""
    sub = session.tail.subscribe(after_seq=after_seq)
    while True:
        try:
            yield await asyncio.wait_for(sub.__anext__(), timeout=15.0)
        except TimeoutError:
            continue
        except StopAsyncIteration:
            return


async def stream_run_live(
    session: RunSession,
    *,
    after: int = 0,
) -> AsyncIterator[bytes]:
    """Retired — P1 uses LcaAgentGateway WebSocket instead of Journal SSE."""
    del session, after
    if False:  # pragma: no cover
        yield b""


def stream_process_journal_live(tail: Any, *, last_seq: int = 0) -> AsyncIterator[bytes]:
    """Provide the process-level Journal stream for operations endpoints."""
    return iter_live_sse(
        tail,
        after_seq=last_seq,
        text_channel=TEXT_CHANNEL_ALL,
    )


__all__ = [
    "iter_stamped_events",
    "stream_chat_completion",
    "stream_process_journal_live",
    "stream_run_live",
]
