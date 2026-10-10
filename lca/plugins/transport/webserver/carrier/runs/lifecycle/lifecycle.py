"""Coordinate execution, pause/resume, and terminal transitions for one run."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager, nullcontext
from typing import Any

import structlog

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.observability import exc_to_record
from lca.contracts.observability.registry.status import RunLifecycleStatus
from lca.contracts.protocols.runtime.infra.infra import MachineResolver
from lca.infrastructure.observability.facade.run.ambit import bind_run_ambit
from lca.infrastructure.observability.spine.exception.emit import (
    emit_exception_caught,
)
from lca.infrastructure.runtime_plane.bindings.bindings import plane_bindings_scope
from lca.infrastructure.runtime_plane.resolve.resolve import PlaneBindingError
from lca.infrastructure.session.emit.runtime_emit import (
    emit_exception_finally as emit_carrier_exception_finally,
)
from lca.infrastructure.workspace import run_workspace_scope
from lca.plugins.events.publish_scope import (
    bind_event_bridge,
    unbind_event_bridge,
)
from lca.plugins.loop.driver.plugin import (
    UnknownExecutionTargetError,
)
from lca.plugins.transport.webserver.carrier.runs.binding import ensure_session_hub
from lca.plugins.transport.webserver.carrier.runs.execute.execution_environment import (
    RunExecutionEnvironment,
)
from lca.plugins.transport.webserver.carrier.runs.run_scopes import run_identity_scopes
from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunRegistry,
    RunSession,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.lifecycle import (
    RunFailureFacts,
    RunOutcomeApplier,
    RunTerminalizer,
    record_run_failure,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.observation import (
    emit_carrier_run_failed,
)
from lca.plugins.transport.webserver.read.runs.live import (
    flush_step_tree_artifacts,
)

_log = structlog.get_logger(__name__)


@contextmanager
def bind_resume_capabilities(session, bindings):
    """Bind the resume capability trio with guaranteed reset (RA-049).

    HIL resume runs without the execution environment that publishes the
    per-turn RuntimePlane handles. Re-publish the hot-cached handles so
    think/fork nodes resolve typed ``bindings`` / ``tools`` ports on the
    resumed traversal. Missing cache (pre-pause-code runs) leaves ports
    unseeded -- same as before this change.

    The three ContextVar bindings (capability_bindings / tools_service /
    defer_session) are set on entry and reset on exit. None-guards are
    preserved: ``capability_bindings`` None skips the whole trio;
    ``tools_service`` None skips tools + defer binding.
    """
    from lca.infrastructure.runtime_plane.capability_bindings import (
        reset_capability_bindings,
        reset_current_tools_service,
        set_capability_bindings,
        set_current_tools_service,
    )
    from lca.infrastructure.tool_defer.policy import DeferPolicy
    from lca.infrastructure.tool_defer.session import (
        ToolDeferSession,
        reset_current_defer_session,
        set_current_defer_session,
    )

    capability_token = None
    tools_token = None
    defer_token = None
    if getattr(session, "capability_bindings", None) is not None:
        capability_token = set_capability_bindings(session.capability_bindings)
        if getattr(session, "tools_service", None) is not None:
            tools_token = set_current_tools_service(session.tools_service)
            # Mirror the create-run policy (ADR-0248): gated vocal
            # mode keeps the ``agent`` namespace eager so the resumed
            # run's vocal contract and visible tool schema agree.
            vocal_mode = getattr(bindings, "vocal_mode", "direct") or "direct"
            defer_token = set_current_defer_session(
                ToolDeferSession(DeferPolicy.for_vocal_mode(vocal_mode))
            )
    try:
        yield
    finally:
        if capability_token is not None:
            reset_capability_bindings(capability_token)
        if tools_token is not None:
            reset_current_tools_service(tools_token)
        if defer_token is not None:
            reset_current_defer_session(defer_token)


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
        session.status = RunLifecycleStatus.RUNNING
        hub = session.hub if session.hub is not None else ensure_session_hub(session, ctx=ctx)
        workspace: Any = None
        success = False
        run_outcome: str = "failure"
        from lca.infrastructure.observability.spine.context.context import SpineContext
        from lca.loop.transport import (
            emit_kernel_run_cancelled,
            emit_kernel_run_start,
            emit_kernel_run_stop,
        )

        SpineContext.set_run(session.run_id)
        # RA-044: the publish+observe bind ritual lives in the
        # lca.plugins.events.publish_scope seam (no private imports here).
        bound_event_session = getattr(session, "event_session", None)
        bridge = (
            getattr(bound_event_session, "bridge", None)
            if bound_event_session is not None
            else None
        )
        publish_token = bind_event_bridge(bridge)

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
                session.workspace = workspace
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
                if not success and outcome.error:
                    from lca.plugins.transport.webserver.read.runs.evidence import (
                        format_user_error,
                    )

                    emit_carrier_run_failed(
                        session,
                        user_message=format_user_error(
                            outcome.error,
                            run_id=session.run_id,
                            trace_id=session.trace_id,
                        ),
                    )
        except (PlaneBindingError, UnknownExecutionTargetError) as exc:
            # RA-048: failure observation converged in _observe_failure.
            user_message = str(exc)
            self._observe_failure(
                session,
                exc,
                boundary="lifecycle.execute",
                hub=hub,
                user_message=user_message,
                emit_finally=True,
            )
        except asyncio.CancelledError:
            session.cancel_requested = True
            session.status = RunLifecycleStatus.CANCELLED
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
            self._observe_failure(
                session,
                exc,
                boundary="lifecycle.execute",
                hub=hub,
                user_message=self._format_exception(exc, session),
                emit_finally=True,
            )
        finally:
            unbind_event_bridge(publish_token)
            emit_kernel_run_stop(
                run_id=session.run_id,
                outcome=run_outcome,
                trace_id=session.trace_id,
            )
            await self._finish_or_pause(session, workspace=workspace, success=success)

    async def resume(self, session: RunSession, *, answer: str) -> None:
        """Resume a paused HIL run while preserving its terminalization policy."""

        from lca.plugins.transport.webserver.carrier.runs.resume import (
            resume_cache_ready,
        )

        if not resume_cache_ready(session):
            raise RuntimeError(
                "durable recovery allows resume but process-local runnable cache is missing"
            )

        success = False
        session.status = RunLifecycleStatus.RUNNING
        # 会话 spine→Session hook 是 task-local ContextVar：fresh run 在其执行
        # 任务里绑定，resume 跑在新任务（HTTP handler create_task），上下文里
        # 没有该 hook，导致 resume 图的 spine 事件与事实全部丢弃
        # （``spine_port_append: no Session hook bound``）。这里在 resume 任务
        # 的上下文里重新绑定，resume 结束后 reset。
        from lca.plugins.session.runtime.spine.hook import (
            bind_bridge_spine_hook,
            reset_bridge_spine_hook,
        )

        # RA-044: see execute() — same publish_scope seam.
        bound = session.event_session
        bridge = getattr(bound, "bridge", None) if bound is not None else None
        spine_hook_token = bind_bridge_spine_hook(bridge) if bridge is not None else None
        publish_token = bind_event_bridge(bridge)
        try:
            bindings = session.bindings
            ambit = session.ambit
            # HIL resume runs without the execution environment that
            # publishes the per-turn RuntimePlane handles. Re-publish the
            # hot-cached handles so think/fork nodes resolve typed
            # ``bindings`` / ``tools`` ports on the resumed traversal.
            # Missing cache (pre-pause-code runs) leaves ports unseeded —
            # same as before this change.
            # RA-049: the capability-bind/reset ritual lives in the
            # bind_resume_capabilities CM; the with-block guarantees reset.
            with (
                bind_resume_capabilities(session, bindings),
                bind_run_ambit(ambit) if ambit is not None else nullcontext(),
                run_identity_scopes(
                    session.run_id,
                    session.attachment_ids or (),
                    getattr(session, "assistant_id", "") or "",
                ),
                run_workspace_scope(session.run_id),
                plane_bindings_scope(bindings) if bindings is not None else nullcontext(),
            ):
                result = await session.runnable.resume(session.snapshot, input=answer)
            # Persist the conclusion text on the session (same as the
            # execute driver) so terminal projection can publish the reply
            # even when the resumed run has no step-tree fold machinery
            # (e.g. a restart-recovered session).
            session.output = getattr(result, "output", "") or ""
            if self._outcomes.apply_resume(session, result):
                self._registry.mark_paused(session)
                return
            success = result.status == TaskStatus.COMPLETED
        except asyncio.CancelledError:
            session.cancel_requested = True
            session.status = RunLifecycleStatus.CANCELLED
            raise
        except Exception as exc:
            _log.exception(
                "run_resume_failed",
                run_id=session.run_id,
                trace_id=session.trace_id,
                error_type=type(exc).__name__,
            )
            # RA-048: resume observes the same ritual minus the finally-emit.
            self._observe_failure(
                session,
                exc,
                boundary="lifecycle.resume",
                hub=session.hub,
                user_message=self._format_exception(exc, session),
                emit_finally=False,
            )
        finally:
            if spine_hook_token is not None:
                reset_bridge_spine_hook(spine_hook_token)
            unbind_event_bridge(publish_token)
            await self._finish_or_pause(session, workspace=None, success=success)

    def _observe_failure(
        self,
        session: RunSession,
        exc: Exception,
        *,
        boundary: str,
        hub: Any,
        user_message: str,
        emit_finally: bool,
    ) -> None:
        """Converged run-failure observation ritual (RA-048).

        ``execute()``'s two ``except`` blocks and ``resume()``'s ``except``
        block all converge here: record the failure facts, emit the
        exception-caught observation, publish the carrier ``run_failed``
        event, and optionally emit the exception-finally observation.  The
        per-path emit set is identical by construction — ``execute()`` passes
        ``emit_finally=True``, ``resume()`` passes ``False``; boundary labels,
        user-message formatting, and the hub stay at the call sites.

        All four emits are synchronous calls, so this seam is sync.
        """
        self._record_failure(session, exc, hub, error=user_message)
        emit_exception_caught(
            exc_to_record(
                exc,
                boundary=boundary,
                run_id=session.run_id,
                trace_id=session.trace_id,
            )
        )
        emit_carrier_run_failed(
            session,
            user_message=user_message,
            exception_class=type(exc).__name__,
        )
        if emit_finally:
            emit_carrier_exception_finally(
                boundary=boundary,
                trace_id=session.trace_id,
            )

    @staticmethod
    def _record_failure(
        session: RunSession,
        exc: BaseException,
        hub: Any,
        *,
        error: str | None = None,
    ) -> None:
        err_msg = error or f"{type(exc).__name__}: {exc}"
        session.error = err_msg
        record_run_failure(
            RunFailureFacts(
                trace_id=session.trace_id,
                run_id=session.run_id,
                agent_role=session.agent.name if session.agent else "",
                strategy_key=session.mode,
                objective=session.user_text,
                error=err_msg,
            )
        )

    @staticmethod
    def _format_exception(exc: Exception, session: RunSession) -> str:
        """Keep exception presentation at the lifecycle error seam."""

        from lca.plugins.transport.webserver.read.runs.evidence import (
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

        if session.status == RunLifecycleStatus.WAITING_INPUT:
            from lca.infrastructure.observability.chat_projection import (
                persist_waiting_projection,
            )
            from lca.plugins.transport.webserver.carrier.runs.recovery import (
                write_resume_bundle,
            )

            await persist_waiting_projection(session)
            # Durable HIL recovery: persist the resume bundle so a kernel
            # restart can rebuild this paused session on the next answer.
            write_resume_bundle(session)
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
            success=success,
        )


__all__ = ["RunLifecycleCoordinator", "ensure_session_hub"]
