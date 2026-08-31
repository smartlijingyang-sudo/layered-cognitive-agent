"""Legacy registry run commands.

This module owns mutations to the legacy ``RunSession`` lifecycle.  Queries and
observability projections deliberately live in :mod:`registry_queries` so the
compatibility facade does not become a second lifecycle owner.
"""

from __future__ import annotations

import asyncio
import contextlib

from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.plugins.transport.webserver.handlers.runs.execute.execute import (
    create_run_session,
    resume_run,
)
from lca.plugins.transport.webserver.handlers.runs.execute.scheduling import (
    schedule_run,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry, RunStatus
from lca.plugins.transport.webserver.handlers.runs.terminal.port import (
    RunCommandReceipt,
    RunReceipt,
    RunRequest,
)


class RegistryRunCommands:
    """Own create, cancel, and approval-resume mutations for registry runs."""

    def __init__(
        self,
        registry: RunRegistry,
        *,
        machine_resolver: MachineResolver | None = None,
    ) -> None:
        self._registry = registry
        self._machine_resolver = machine_resolver

    async def create_and_dispatch(self, request: RunRequest) -> RunReceipt:
        self._registry.prune()
        session = self._registry.find_inflight_run(
            user_text=request.user_text,
            mode=request.mode,
            attachment_ids=request.attachment_ids,
            agent_id=request.agent.agent_id,
        )
        if session is None:
            session = create_run_session(
                self._registry,
                question=request.question,
                user_text=request.user_text,
                mode=request.mode,
                attachment_ids=request.attachment_ids,
                prior_turns=request.prior_turns,
                agent=request.agent,
                device_id=request.device_id,
                plane=request.plane,
                extra_plane=request.extra_plane,
                execution_target=request.execution_target,
                ctx=request.ctx,
            )
            schedule_run(
                self._registry,
                session,
                ctx=request.ctx,
                machine_resolver=self._machine_resolver,
            )
        return RunReceipt(run_id=session.run_id, trace_id=session.trace_id, accepted=True)

    async def cancel(self, run_id: str) -> RunCommandReceipt:
        session = self._registry.get(run_id)
        if session is None:
            return RunCommandReceipt(accepted=False, error="run not found")
        if session.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED):
            return RunCommandReceipt(accepted=True, status=session.status.value)
        session.cancel_requested = True
        session.status = RunStatus.CANCELED
        if session.task is not None and not session.task.done():
            session.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.task
        return RunCommandReceipt(accepted=True, status=RunStatus.CANCELED.value)

    async def resume_approval(
        self,
        run_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> RunCommandReceipt:
        del approval_id, idempotency_key
        if not isinstance(payload, str):
            return RunCommandReceipt(
                accepted=False,
                error="approval payload must be a string",
                error_status=400,
            )
        session = self._registry.get(run_id)
        if session is None:
            return RunCommandReceipt(accepted=False, error="run not found")
        if session.status is not RunStatus.WAITING_INPUT:
            return RunCommandReceipt(
                accepted=False,
                error="run not waiting for input",
                error_status=409,
            )
        if session.snapshot is None or session.runnable is None:
            return RunCommandReceipt(
                accepted=False,
                error="no resume state available",
                error_status=500,
            )
        session.status = RunStatus.RUNNING
        session.task = asyncio.create_task(resume_run(session, self._registry, payload))
        return RunCommandReceipt(accepted=True, status="resumed")


__all__ = ["RegistryRunCommands"]
