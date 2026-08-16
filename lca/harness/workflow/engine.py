"""Concurrent dependency-aware workflow executor."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from lca.contracts.harness.workflow import (
    WorkflowMeta,
    WorkflowPhase,
    WorkflowPhaseContext,
    WorkflowProgress,
)

PhaseWorker = Callable[[WorkflowPhaseContext], Awaitable[Any]]
ProgressObserver = Callable[[WorkflowProgress], None]


class WorkflowEngine:
    """Runs each ready DAG phase in an isolated ``asyncio.Task``."""

    def __init__(self) -> None:
        self._progress = WorkflowProgress((), ())

    @property
    def progress(self) -> WorkflowProgress:
        """Latest immutable progress snapshot for the current or last run."""
        return self._progress

    def validate(self, meta: WorkflowMeta) -> None:
        phases = {phase.name: phase for phase in meta.phases}
        if not meta.name or not meta.phases or len(phases) != len(meta.phases):
            raise ValueError("workflow needs a name and uniquely named phases")
        for phase in meta.phases:
            unknown = set(phase.deps) - phases.keys()
            if unknown:
                raise ValueError(f"phase {phase.name} depends on unknown phases: {sorted(unknown)}")
        pending = {phase.name: set(phase.deps) for phase in meta.phases}
        complete: set[str] = set()
        while pending:
            ready = {name for name, deps in pending.items() if deps <= complete}
            if not ready:
                raise ValueError("workflow contains a dependency cycle")
            complete.update(ready)
            for name in ready:
                pending.pop(name)

    async def run(
        self,
        meta: WorkflowMeta,
        worker: PhaseWorker,
        *,
        on_progress: ProgressObserver | None = None,
    ) -> dict[str, Any]:
        self.validate(meta)
        phases = {phase.name: phase for phase in meta.phases}
        results: dict[str, Any] = {}
        pending = set(phases)
        self._publish_progress(results, pending, on_progress)
        while pending:
            ready = sorted(name for name in pending if set(phases[name].deps) <= results.keys())
            tasks = {
                name: asyncio.create_task(self._run_phase(meta, phases[name], results, worker))
                for name in ready
            }
            try:
                values = await asyncio.gather(*tasks.values())
            except BaseException:
                for task in tasks.values():
                    task.cancel()
                await asyncio.gather(*tasks.values(), return_exceptions=True)
                raise
            results.update(zip(tasks, values, strict=True))
            pending.difference_update(tasks)
            self._publish_progress(results, pending, on_progress)
        return results

    def _publish_progress(
        self,
        results: dict[str, Any],
        pending: set[str],
        observer: ProgressObserver | None,
    ) -> None:
        self._progress = WorkflowProgress(tuple(sorted(results)), tuple(sorted(pending)))
        if observer is not None:
            observer(self._progress)

    @staticmethod
    async def _run_phase(
        meta: WorkflowMeta,
        phase: WorkflowPhase,
        results: dict[str, Any],
        worker: PhaseWorker,
    ) -> Any:
        dependencies = {name: results[name] for name in phase.deps}
        return await worker(WorkflowPhaseContext(meta, phase, dependencies))
