"""Coordinate execution, pause/resume, and terminal transitions for one run."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import Any

import structlog

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.observability import exc_to_record
from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.infrastructure.observability.facade.run_ambit import bind_run_ambit
from lca.infrastructure.runtime_plane.resolve import PlaneBindingError
from lca.infrastructure.runtime_plane.scope import plane_bindings_scope
from lca.infrastructure.workspace import run_workspace_scope
from lca.plugins.loop_drivers.registry import (
    _UnknownExecutionTargetError as _UnknownExecutionTargetError,
)
from lca.plugins.transport.webserver.handlers.runs.execute.execution_environment import (
    RunExecutionEnvironment,
)
from lca.plugins.transport.webserver.handlers.runs.observability.binding import ensure_session_hub
from lca.plugins.transport.webserver.handlers.runs.observability.step_tree_flush import (
    flush_step_tree_artifacts,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import (
    RunRegistry,
    RunSession,
    RunStatus,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.failure import (
    RunFailureFacts,
    record_run_failure,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.outcome import RunOutcomeApplier
from lca.plugins.transport.webserver.handlers.runs.terminal.terminalizer import RunTerminalizer

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
        run_outcome: str = "failure"
        from lca.infrastructure.observability.spine.context import SpineContext
        from lca.infrastructure.observability.spine.exception_emit import (
            emit_exception_caught,
        )
        from lca.plugins.events.publishers.spine_reflector_runtime import (
            emit_exception_finally as emit_carrier_exception_finally,
        )
        from lca.plugins.events.publishers.spine_reflector_transport import (
            emit_kernel_run_cancelled,
            emit_kernel_run_start,
            emit_kernel_run_stop,
        )

        SpineContext.set_run(session.run_id)
        emit_kernel_run_start(run_id=session.run_id, trace_id=session.trace_id)
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
                    run_outcome = "success"
                    return
                success = outcome.success
                run_outcome = "success" if success else "failure"
        except (PlaneBindingError, _UnknownExecutionTargetError) as exc:
            session.error = str(exc)
            self._record_failure(session, exc, hub)
            emit_exception_caught(
                exc_to_record(
                    exc,
                    boundary="lifecycle.execute",
                    run_id=session.run_id,
                    trace_id=session.trace_id,
                )
            )
            emit_carrier_exception_finally(
                boundary="lifecycle.execute",
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
        except asyncio.CancelledError:
            session.cancel_requested = True
            session.status = RunStatus.CANCELED
            emit_kernel_run_cancelled(run_id=session.run_id, trace_id=session.trace_id)
            run_outcome = "cancelled"
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
            emit_exception_caught(
                exc_to_record(
                    exc,
                    boundary="lifecycle.execute",
                    run_id=session.run_id,
                    trace_id=session.trace_id,
                )
            )
            emit_carrier_exception_finally(
                boundary="lifecycle.execute",
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
        finally:
            emit_kernel_run_stop(
                run_id=session.run_id,
                outcome=run_outcome,  # type: ignore[arg-type]
                trace_id=session.trace_id,
            )
            await self._finish_or_pause(session, workspace=workspace, success=success)

    async def resume(self, session: RunSession, *, answer: str) -> None:
        """Resume a paused HIL run while preserving its terminalization policy."""

        success = False
        session.status = RunStatus.RUNNING
        try:
            bindings = session.bindings
            ambit = session.ambit
            # Re-enter the run's ambient environment for the resumed turn: the
            # FileStore (prompt rendering), workspace, and plane bindings all
            # reset when the pausing turn's scopes exit, so bind them again.
            with (
                bind_run_ambit(ambit) if ambit is not None else nullcontext(),
                run_workspace_scope(session.run_id),
                plane_bindings_scope(bindings) if bindings is not None else nullcontext(),
            ):
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

        from lca.plugins.transport.webserver.handlers.runs.observability.error_presentation import (
            format_user_error,
        )

        return format_user_error(
            f"{type(exc).__name__}: {exc}",
            run_id=session.run_id,
            trace_id=session.trace_id,
        )

    async def _finish_or_pause(self, session: RunSession, *, workspace: Any, success: bool) -> None:
        """Leave a pause resumable or terminalize all other lifecycle outcomes.

        Pause is an incremental derive point: journal.json + narrative.md are
        flushed here (outcome ``paused``) so derived artifacts exist while the
        run waits for input, not only after a terminal transition.  A paused
        run that is later canceled must not depend on terminalize to have any
        derived artifacts on disk.
        """

        if session.status == RunStatus.WAITING_INPUT:
            flush_errors = flush_step_tree_artifacts(session, outcome="paused")
            if flush_errors:
                _log.warning(
                    "step_tree_flush_on_pause_failed",
                    run_id=session.run_id,
                    flush_errors=flush_errors,
                )
            self._registry.mark_paused(session)
            return
        await RunTerminalizer(self._registry).terminalize(
            session,
            workspace=workspace,
            success=success,
        )


__all__ = ["RunLifecycleCoordinator", "ensure_session_hub"]
