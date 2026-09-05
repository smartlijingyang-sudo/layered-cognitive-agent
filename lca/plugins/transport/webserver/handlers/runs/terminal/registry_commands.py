"""Legacy registry run commands.

This module owns mutations to the legacy ``RunSession`` lifecycle.  Queries and
observability projections deliberately live in :mod:`registry_queries` so the
compatibility facade does not become a second lifecycle owner.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog

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

_log = structlog.get_logger(__name__)


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
                assistant_id=request.assistant_id or "",
                ctx=request.ctx,
            )
            schedule_run(
                self._registry,
                session,
                ctx=request.ctx,
                machine_resolver=self._machine_resolver,
            )
        # Bind SpineContext as soon as run_id exists so subsequent
        # kernel.run.* / exception.* land in traces/runs/<id>/<run_id>.spine.jsonl.
        from lca.infrastructure.observability.spine.context import SpineContext

        SpineContext.set_run(session.run_id)
        return RunReceipt(run_id=session.run_id, trace_id=session.trace_id, accepted=True)

    async def cancel(self, run_id: str) -> RunCommandReceipt:
        session = self._registry.get(run_id)
        if session is None:
            _log.warning("run_cancel_rejected", run_id=run_id, reason="run_not_found")
            return RunCommandReceipt(accepted=False, error="run not found")
        if session.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED):
            _log.info("run_cancel_noop", run_id=run_id, status=session.status.value)
            return RunCommandReceipt(accepted=True, status=session.status.value)
        prior_status = session.status
        session.cancel_requested = True
        session.status = RunStatus.CANCELED
        if session.task is not None and not session.task.done():
            session.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.task
        _log.info(
            "run_canceled",
            run_id=run_id,
            prior_status=prior_status.value,
            canceled_at_waiting_input=prior_status is RunStatus.WAITING_INPUT,
        )
        return RunCommandReceipt(accepted=True, status=RunStatus.CANCELED.value)

    async def resume_approval(
        self,
        run_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> RunCommandReceipt:
        if not isinstance(payload, str):
            _log.warning(
                "run_resume_rejected",
                run_id=run_id,
                reason="payload_not_string",
                idempotency_key=idempotency_key,
            )
            return RunCommandReceipt(
                accepted=False,
                error="approval payload must be a string",
                error_status=400,
            )
        session = self._registry.get(run_id)
        if session is None:
            _log.warning(
                "run_resume_rejected",
                run_id=run_id,
                reason="run_not_found",
                idempotency_key=idempotency_key,
            )
            return RunCommandReceipt(accepted=False, error="run not found")
        if idempotency_key and idempotency_key in session.accepted_answer_keys:
            _log.info(
                "run_resume_replayed",
                run_id=run_id,
                idempotency_key=idempotency_key,
            )
            return RunCommandReceipt(accepted=True, status="resumed")
        if session.status is not RunStatus.WAITING_INPUT:
            _log.warning(
                "run_resume_rejected",
                run_id=run_id,
                reason="not_waiting_input",
                status=session.status.value,
                idempotency_key=idempotency_key,
            )
            return RunCommandReceipt(
                accepted=False,
                error="run not waiting for input",
                error_status=409,
            )
        if session.snapshot is None or session.runnable is None:
            _log.warning(
                "run_resume_rejected",
                run_id=run_id,
                reason="no_resume_state",
                idempotency_key=idempotency_key,
            )
            return RunCommandReceipt(
                accepted=False,
                error="no resume state available",
                error_status=500,
            )
        pending_approval_id = ""
        if session.approval_request is not None:
            raw_pending = session.approval_request.get("approval_id")
            pending_approval_id = str(raw_pending) if raw_pending else ""
        session.status = RunStatus.RUNNING
        if idempotency_key:
            session.accepted_answer_keys.add(idempotency_key)
        # The frontend still posts the tool name as approval_id; the pending
        # approval carries the derived "<plan_ref>:<node>:<visit>" id. Record
        # both plus the match flag so mismatches stay auditable.
        _log.info(
            "run_resume_accepted",
            run_id=run_id,
            idempotency_key=idempotency_key,
            request_approval_id=approval_id,
            pending_approval_id=pending_approval_id,
            approval_id_matched=bool(pending_approval_id) and approval_id == pending_approval_id,
            payload_chars=len(payload),
        )
        # Resume 是新请求 = 新 context：create 时的 Session 绑定不在场。
        # create_task 拷贝当前 context，run task 继承这里的绑定；
        # 请求 context 随请求结束丢弃，无需 reset。
        bound = session.event_session
        if bound is not None:
            from lca.plugins.events._session_observe import set_session
            from lca.plugins.events.publishers._session_publish import (
                set_publish_session,
            )

            set_publish_session(bound.bridge)
            set_session(bound.bridge)
        session.task = asyncio.create_task(resume_run(session, self._registry, payload))
        return RunCommandReceipt(accepted=True, status="resumed")


__all__ = ["RegistryRunCommands"]
