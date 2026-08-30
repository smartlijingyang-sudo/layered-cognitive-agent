"""Coordinate execution, pause/resume, and terminal transitions for one run."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import Any

import structlog

from gateway.runs.execute.execution_environment import RunExecutionEnvironment
from gateway.runs.observability.binding import ensure_session_hub
from gateway.runs.session.session import RunRegistry, RunSession, RunStatus
from gateway.runs.terminal.failure import RunFailureFacts, record_run_failure
from gateway.runs.terminal.outcome import RunOutcomeApplier
from gateway.runs.terminal.terminalizer import RunTerminalizer
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.infrastructure.runtime_plane.resolve import PlaneBindingError
from lca.infrastructure.runtime_plane.scope import plane_bindings_scope
from lca.plugins.loop_drivers.registry import (
    _UnknownExecutionTargetError as _UnknownExecutionTargetError,
)

_log = structlog.get_logger(__name__)


class RunLifecycleCoordinator:
    """Coordinate run lifecycle while delegating result translation and closure.

    Execution environment preparation, outcome-to-session translation, failure
    observation, and terminalization each have their own seam.  This class only
    sequences those collaborators and owns lifecycle transitions.
    """

    def __init__(
        self,
        registry: RunRegistry,
        *,
        machine_resolver: MachineResolver | None = None,
        outcomes: RunOutcomeApplier | None = None,
    ) -> None:
        self._registry = registry
        self._machine_resolver = machine_resolver
        self._outcomes = outcomes or RunOutcomeApplier()

    async def execute(
        self,
        *,
        run_id: str,
        question: str,
        mode: str,
        ctx: Any,
    ) -> None:
        """Execute a registered run through its prepared loop driver."""

        session = self._registry.get(run_id)
        if session is None:
            return
        session.status = RunStatus.RUNNING
        hub = session.hub if session.hub is not None else ensure_session_hub(session, ctx=ctx)
        workspace: Any = None
        success = False
        try:
            environment = RunExecutionEnvironment(
                session,
                ctx=ctx,
                hub=hub,
                machine_resolver=self._machine_resolver,
            )
            async with environment.prepare() as prepared:
                workspace = prepared.workspace
                outcome = await prepared.driver.execute(
                    session,
                    question=question,
                    mode=mode,
                    hub=hub,
                    bindings=prepared.bindings,
                    run_context=prepared.run_context,
                    ctx=ctx,
                    machine_resolver=self._machine_resolver,
                )
                if self._outcomes.apply_driver(session, outcome):
                    _log.info(
                        "run_paused_for_input",
                        hop="H2",
                        run_id=session.run_id,
                        approval_type=session.approval_request.get("type")
                        if session.approval_request
                        else None,
                    )
                    return
                success = outcome.success
        except (PlaneBindingError, _UnknownExecutionTargetError) as exc:
            session.error = str(exc)
            self._record_failure(session, exc, hub)
        except asyncio.CancelledError:
            session.cancel_requested = True
            session.status = RunStatus.CANCELED
            raise
        except Exception as exc:
            _log.exception(
                "run_failed",
                run_id=session.run_id,
                trace_id=session.trace_id,
                error_type=type(exc).__name__,
            )
            session.error = self._format_exception(exc, session)
            self._record_failure(session, exc, hub)
        finally:
            await self._finish_or_pause(session, workspace=workspace, success=success)

    async def resume(self, session: RunSession, *, answer: str) -> None:
        """Resume a paused HIL run while preserving its terminalization policy."""

        success = False
        session.status = RunStatus.RUNNING
        try:
            bindings = session.bindings
            scope = plane_bindings_scope(bindings) if bindings is not None else nullcontext()
            with scope:
                result = await session.runnable.resume(session.snapshot, input=answer)
            if self._outcomes.apply_resume(session, result):
                self._registry.mark_paused(session)
                return
            success = result.status == TaskStatus.COMPLETED
        except asyncio.CancelledError:
            session.cancel_requested = True
            session.status = RunStatus.CANCELED
            raise
        except Exception as exc:
            _log.exception(
                "run_resume_failed",
                run_id=session.run_id,
                trace_id=session.trace_id,
                error_type=type(exc).__name__,
            )
            session.error = self._format_exception(exc, session)
            self._record_failure(session, exc, session.hub)
        finally:
            await self._finish_or_pause(session, workspace=None, success=success)

    @staticmethod
    def _record_failure(session: RunSession, exc: BaseException, hub: Any) -> None:
        """Project mutable lifecycle state into the observation seam."""

        record_run_failure(
            RunFailureFacts(
                trace_id=session.trace_id,
                run_id=session.run_id,
                agent_role=session.agent.name if session.agent else "",
                strategy_key=session.mode,
                objective=session.user_text,
                error=session.error or f"{type(exc).__name__}: {exc}",
                hub=hub,
            )
        )

    @staticmethod
    def _format_exception(exc: Exception, session: RunSession) -> str:
        """Keep exception presentation at the lifecycle error seam."""

        from gateway.runs.observability.error_presentation import format_user_error

        return format_user_error(
            f"{type(exc).__name__}: {exc}",
            run_id=session.run_id,
            trace_id=session.trace_id,
        )

    async def _finish_or_pause(self, session: RunSession, *, workspace: Any, success: bool) -> None:
        """Leave a pause resumable or terminalize all other lifecycle outcomes."""

        if session.status == RunStatus.WAITING_INPUT:
            self._registry.mark_paused(session)
            return
        await RunTerminalizer(self._registry).terminalize(
            session,
            workspace=workspace,
            success=success,
        )


__all__ = ["RunLifecycleCoordinator", "ensure_session_hub"]
