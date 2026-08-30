"""Read-side projections for the registry run path."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from gateway.runs.doctor import DoctorReport, diagnose
from gateway.runs.session import RunRegistry
from lca.layer0_infra.observability.journal.live_tail import (
    TEXT_CHANNEL_ALL,
    TEXT_CHANNEL_ANSWER,
    LiveGap,
    iter_live_sse,
)


class RegistryRunQueries:
    """Own read-only run projections and process-level observability streams."""

    def __init__(self, registry: RunRegistry) -> None:
        self._registry = registry

    async def summary(self, run_id: str) -> dict[str, Any] | None:
        self._registry.prune()
        return self._registry.summary(run_id)

    async def stream_chat_completion(self, run_id: str, last_seq: int = 0) -> AsyncIterator[bytes]:
        """Stream a run's journal events encoded as OpenAI ChatCompletion chunks.

        ADR-0099: single SSE connection, OpenAI ChatCompletion streaming format.
        """
        from lca.plugins.providers.openai_stream_encoder import (
            OpenAIChatChunkBuilder,
            OpenAIStreamEncoder,
        )

        session = self._registry.get(run_id)
        if session is None:
            return
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
                for sub in list(session.tail._subscribers):
                    with contextlib.suppress(Exception):
                        sub.queue.put_nowait(None)

    async def iter_stamped_events(self, run_id: str, after_seq: int = 0) -> AsyncIterator[Any]:
        """Yield the raw ``StampedEvent`` stream for one run.

        Subscribes to the live tail and yields each item including
        ``LiveGap`` markers so callers can decide whether to terminate.
        """
        session = self._registry.get(run_id)
        if session is None:
            return
        sub = session.tail.subscribe(after_seq=after_seq)
        while True:
            try:
                yield await asyncio.wait_for(sub.__anext__(), timeout=15.0)
            except asyncio.TimeoutError:
                continue
            except StopAsyncIteration:
                return

    async def stream_run_live(self, run_id: str, after: int = 0) -> AsyncIterator[bytes]:
        """Stream a run's journal as Journal SSE (event = class name)."""
        session = self._registry.get(run_id)
        if session is None:
            return
        try:
            async for line in iter_live_sse(
                session.tail,
                after_seq=after,
                text_channel=TEXT_CHANNEL_ANSWER,
            ):
                yield line
        except asyncio.CancelledError:
            return

    async def doctor(self, run_id: str) -> DoctorReport | None:
        session = self._registry.get(run_id)
        jsonl_path = (
            session.jsonl_path if session is not None else self._registry.jsonl_path_for(run_id)
        )
        if session is None and not jsonl_path.is_file():
            return None
        return diagnose(session, jsonl_path)

    def journal_path(self, run_id: str) -> Path | None:
        """Return only the current run's Journal path; never fall back across sessions."""
        path = self._registry.jsonl_path_for(run_id)
        return path if path.is_file() else None

    def latest_bindings(self) -> object | None:
        """Expose the context projection without exposing the Registry itself."""
        return self._registry.latest_bindings()

    def status_counts(self) -> dict[str, int]:
        return self._registry.status_counts()

    def live_totals(self) -> dict[str, int]:
        return self._registry.live_totals()

    def stream_process_journal_live(self, last_seq: int = 0) -> AsyncIterator[bytes]:
        """Provide the process-level Journal stream for operations endpoints."""
        return iter_live_sse(
            self._registry.journal.tail,
            after_seq=last_seq,
            text_channel=TEXT_CHANNEL_ALL,
        )


class _StampedShim:
    """Adapter so ``OpenAIStreamEncoder`` can dispatch on dict-backed stamps."""

    def __init__(self, stamped: Any) -> None:
        self._stamped = stamped

    def __getattr__(self, name: str) -> Any:
        data = getattr(self._stamped, "data", None) or {}
        if isinstance(data, dict) and name in data:
            return data[name]
        return getattr(self._stamped, name, "")


__all__ = ["RegistryRunQueries"]
