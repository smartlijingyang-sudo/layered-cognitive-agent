"""Run live SSE streams, process journal projection binding, and step tree flushing.

Consolidates:
- Process-wide journal projection binding and subscriber count tracking
- Step-tree artifact flushing (journal.json + narrative.md) and outcome resolution
- Live event streaming and OpenAI ChatCompletion chunk encoding
"""

from __future__ import annotations

import asyncio
import contextlib
import traceback
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import structlog

from lca.contracts.observability.journal.run_journal import (
    ProcessJournalProjection,
    RunJournalFactory,
)
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability.journal.stream.live_tail import (
    TEXT_CHANNEL_ALL,
    LiveGap,
    iter_live_sse,
)

if TYPE_CHECKING:
    from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession

_log = structlog.get_logger(__name__)


# --- Process Journal Binding ---


class ProcessJournalBinding:
    """Lazily close the one process projection shared by all legacy runs."""

    def __init__(self) -> None:
        self._journal: ProcessJournalProjection | None = None

    @property
    def journal(self) -> ProcessJournalProjection:
        """Return the bound projection or reject an implicit default."""
        if self._journal is None:
            raise RuntimeError(
                "process journal is not bound; create a run through a journal factory"
            )
        return self._journal

    def bind(self, factory: RunJournalFactory) -> JournalProjector:
        """Create the projection once and return a per-run append binding."""
        if self._journal is None:
            self._journal = factory.create_process_journal()
        return self._journal.bind()

    @property
    def subscriber_count(self) -> int:
        """Expose live subscription pressure without leaking the projection field."""
        return self._journal.tail.subscriber_count if self._journal is not None else 0


# --- Step Tree Artifact Flushing ---


def journal_outcome_from_session(session: RunSession) -> str:
    """Map RunSession.status onto JournalMetadata.outcome vocabulary."""
    status = str(getattr(session.status, "value", session.status) or "").lower()
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    if status in {"canceled", "cancelled"}:
        return "stopped"
    if status == "waiting_input":
        return "paused"
    return "stopped"


def flush_step_tree_artifacts(
    session: RunSession,
    *,
    outcome: str | None = None,
) -> list[dict[str, str]]:
    """Fold 事件流并写 journal.json + narrative.md;返回 flush_errors."""
    bundle = getattr(session, "step_tree_bundle", None)
    if bundle is None:
        return []
    errors: list[dict[str, str]] = []
    try:
        resolved = outcome if outcome is not None else journal_outcome_from_session(session)
        flush = getattr(bundle, "flush", None)
        if callable(flush):
            flush(outcome=resolved)
    except Exception as exc:
        errors.append(
            {
                "operation": "step_tree.flush",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        _log.warning(
            "step_tree_flush_failed",
            run_id=getattr(session, "run_id", ""),
            outcome=resolved,
            error=str(exc),
        )
    return errors


# --- Live Streams ---


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


async def stream_run_fold(
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
    "ProcessJournalBinding",
    "flush_step_tree_artifacts",
    "iter_stamped_events",
    "journal_outcome_from_session",
    "stream_chat_completion",
    "stream_process_journal_live",
    "stream_run_fold",
]
