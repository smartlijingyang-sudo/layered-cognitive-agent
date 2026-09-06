"""Read-side projections for the registry run path (ADR-0195 P3-07/P3-09)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from lca.plugins.transport.webserver.doctor import DoctorReport, diagnose
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunRegistry
from lca.plugins.transport.webserver.read.runs import live as run_live


class RegistryRunQueries:
    """Own read-only run projections and process-level observability streams."""

    def __init__(self, registry: RunRegistry) -> None:
        self._registry = registry

    async def summary(self, run_id: str) -> dict[str, Any] | None:
        self._registry.prune()
        return self._registry.summary(run_id)

    async def stream_chat_completion(self, run_id: str, last_seq: int = 0) -> AsyncIterator[bytes]:
        """Stream a run's journal events encoded as OpenAI ChatCompletion chunks."""
        session = self._registry.get(run_id)
        if session is None:
            return
        async for line in run_live.stream_chat_completion(session, last_seq=last_seq):
            yield line

    async def iter_stamped_events(self, run_id: str, after_seq: int = 0) -> AsyncIterator[Any]:
        """Yield the raw ``StampedEvent`` stream for one run."""
        session = self._registry.get(run_id)
        if session is None:
            return
        async for item in run_live.iter_stamped_events(session, after_seq=after_seq):
            yield item

    async def stream_run_live(self, run_id: str, after: int = 0) -> AsyncIterator[bytes]:
        """Stream a run live as four UI SSE events (reasoning|text|tool|done)."""
        session = self._registry.get(run_id)
        if session is None:
            return
        async for line in run_live.stream_run_live(session, after=after):
            yield line

    async def doctor(self, run_id: str) -> DoctorReport | None:
        session = self._registry.get(run_id)
        spine_path = (
            session.spine_path if session is not None else self._registry.spine_path_for(run_id)
        )
        if session is None and not spine_path.is_file():
            return None
        return diagnose(session, spine_path)

    def journal_path(self, run_id: str) -> Path | None:
        """Return only the current run's spine path; never fall back across sessions."""
        path = self._registry.spine_path_for(run_id)
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
        return run_live.stream_process_journal_live(
            self._registry.journal.tail,
            last_seq=last_seq,
        )


__all__ = ["RegistryRunQueries"]
