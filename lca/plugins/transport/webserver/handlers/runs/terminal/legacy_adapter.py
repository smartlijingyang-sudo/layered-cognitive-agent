"""Legacy registry-backed ``/runs`` facade.

The facade preserves the stable RunPort vocabulary while keeping ownership
explicit: lifecycle mutations live in ``RegistryRunCommands`` and read-side
projections live in ``RegistryRunQueries``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.plugins.transport.webserver.handlers.runs.doctor import DoctorReport
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry
from lca.plugins.transport.webserver.handlers.runs.terminal.port import (
    RunCommandReceipt,
    RunReceipt,
    RunRequest,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.registry_commands import (
    RegistryRunCommands,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.registry_queries import (
    RegistryRunQueries,
)


class RegistryRunAdapter:
    """Compatibility facade over separately owned registry commands and queries."""

    def __init__(
        self,
        registry: RunRegistry,
        *,
        machine_resolver: MachineResolver | None = None,
    ) -> None:
        self._commands = RegistryRunCommands(
            registry,
            machine_resolver=machine_resolver,
        )
        self._queries = RegistryRunQueries(registry)

    async def create_and_dispatch(self, request: RunRequest) -> RunReceipt:
        return await self._commands.create_and_dispatch(request)

    async def cancel(self, run_id: str) -> RunCommandReceipt:
        return await self._commands.cancel(run_id)

    async def resume_approval(
        self,
        run_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> RunCommandReceipt:
        return await self._commands.resume_approval(
            run_id,
            approval_id,
            payload,
            idempotency_key,
        )

    async def summary(self, run_id: str) -> dict[str, Any] | None:
        return await self._queries.summary(run_id)

    async def stream_chat_completion(self, run_id: str, last_seq: int = 0) -> AsyncIterator[bytes]:
        """ADR-0099: OpenAI ChatCompletion streaming wire per run."""
        async for line in self._queries.stream_chat_completion(run_id, last_seq):
            yield line

    async def iter_stamped_events(self, run_id: str, after_seq: int = 0) -> AsyncIterator[Any]:
        """Forward ``RegistryRunQueries.iter_stamped_events``."""
        async for stamped in self._queries.iter_stamped_events(run_id, after_seq):
            yield stamped

    async def stream_run_live(self, run_id: str, after: int = 0) -> AsyncIterator[bytes]:
        """Journal SSE per run (event = class name)."""
        async for line in self._queries.stream_run_live(run_id, after):
            yield line

    async def doctor(self, run_id: str) -> DoctorReport | None:
        return await self._queries.doctor(run_id)

    def journal_path(self, run_id: str) -> Path | None:
        return self._queries.journal_path(run_id)

    def latest_bindings(self) -> object | None:
        return self._queries.latest_bindings()

    def status_counts(self) -> dict[str, int]:
        return self._queries.status_counts()

    def live_totals(self) -> dict[str, int]:
        return self._queries.live_totals()

    def stream_process_journal_live(self, last_seq: int = 0) -> AsyncIterator[bytes]:
        return self._queries.stream_process_journal_live(last_seq)


__all__ = ["RegistryRunAdapter"]
