"""Orchestrate one DSH turn: runtime → archive + journal projection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols import DshRuntime
from lca.infrastructure.comparison.dsh_driver.models import DshNotification, DshTurnResult
from lca.infrastructure.comparison.dsh_driver.ports import DshEventArchive
from lca.infrastructure.comparison.dsh_driver.projector import DshJournalProjector


@dataclass(frozen=True)
class DshTurnSpec:
    prompt: str
    session_id: str
    cwd: str
    session_root: str
    harness_env: dict[str, str] | None = None


class DshTurnDriver:
    """Template method: notify → persist raw → project → return result."""

    def __init__(
        self,
        runtime: DshRuntime,
        projector: DshJournalProjector,
        archive: DshEventArchive,
    ) -> None:
        self._runtime = runtime
        self._projector = projector
        self._archive = archive

    def _on_event(self, notification: DshNotification) -> None:
        self._archive.append(notification)
        self._projector.feed(notification)

    def _finish(self, result: DshTurnResult) -> DshTurnResult:
        status = (
            TaskStatus.COMPLETED
            if result.finish_reason in {None, TaskStatus.COMPLETED}
            else TaskStatus.FAILED
        )
        self._projector.emit_terminal_event(
            status=status,
            output=result.final_response,
            error="" if status == TaskStatus.COMPLETED else (result.finish_reason or "error"),
        )
        return result

    def run(self, spec: DshTurnSpec) -> DshTurnResult:
        result = self._runtime.run_turn(spec, self._on_event)
        return self._finish(result)

    async def run_async(self, spec: DshTurnSpec) -> DshTurnResult:
        runtime = self._runtime
        run_async = getattr(runtime, "run_turn_async", None)
        if callable(run_async):
            result = await run_async(spec, self._on_event)
        else:
            result = await asyncio.to_thread(self._runtime.run_turn, spec, self._on_event)
        return self._finish(result)
