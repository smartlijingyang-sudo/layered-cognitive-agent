"""Task scheduling for the legacy ``/runs`` carrier.

Scheduling is deliberately kept separate from run execution.  The execution
facade owns lifecycle semantics; this module owns the asyncio task handle and
its cancellation bookkeeping at the carrier seam.
"""

from __future__ import annotations

import asyncio
from typing import Any

from gateway.runs.session.session import RunRegistry, RunSession, RunStatus
from lca.contracts.protocols.infra import MachineResolver


async def _execute(
    registry: RunRegistry,
    session: RunSession,
    *,
    ctx: Any,
    machine_resolver: MachineResolver | None,
) -> None:
    """Load the execution seam lazily to keep scheduling independent of setup."""

    from gateway.runs.lifecycle import RunLifecycleCoordinator

    await RunLifecycleCoordinator(
        registry,
        machine_resolver=machine_resolver,
    ).execute(
        run_id=session.run_id,
        question=session.question,
        mode=session.mode,
        ctx=ctx,
    )


def schedule_run(
    registry: RunRegistry,
    session: RunSession,
    *,
    ctx: Any,
    machine_resolver: MachineResolver | None = None,
) -> asyncio.Task[Any]:
    """Schedule one run and record cancellation on its session.

    The returned task is the sole carrier for asynchronous execution.  This
    keeps task lifecycle policy local to the scheduling module instead of
    leaking it into the run lifecycle or session setup modules.
    """

    task = asyncio.create_task(
        _execute(
            registry,
            session,
            ctx=ctx,
            machine_resolver=machine_resolver,
        )
    )
    session.task = task

    def _mark_cancelled(done: asyncio.Task[Any]) -> None:
        if done.cancelled() or done.cancelling() > 0:
            session.status = RunStatus.CANCELED
            session.cancel_requested = True

    task.add_done_callback(_mark_cancelled)
    return task


__all__ = ["schedule_run"]
