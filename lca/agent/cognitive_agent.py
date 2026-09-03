"""CognitiveAgent — single agent runtime unit."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from lca.contracts.mechanisms import Hook
from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.message import (
    AgentMessage,
    agent_message_as_text,
    agent_message_text,
)
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import StateSnapshot
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    RunScope,
)
from lca.contracts.models.observability.plan_ref import plan_ref_scope
from lca.contracts.models.team.partial_buffer import (
    begin_partial_buffer,
    drain_run_partial,
    reset_partial_buffer,
)
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols import AgentUnit, Runtime
from lca.contracts.protocols.perceive.capabilities import HasHooks
from lca.infrastructure.observability import (
    BoundObservability,
    adopt_run_scope,
    bind_backends,
    objective_preview,
    record,
    run_scope,
    set_session,
)
from lca.infrastructure.workspace import effective_agent_wall_clock, get_run_workspace
from lca.runtime.runtime_lifecycle import record_run_resumed

_STRATEGY_KEY_SOLO = "solo"


def _task_as_text(task: str | AgentMessage) -> str:
    if isinstance(task, AgentMessage):
        return agent_message_as_text(task)
    return task


class CognitiveAgent(AgentUnit):
    """Runtime + RoleProfile as a schedulable unit with run / resume / cancel."""

    def __init__(
        self,
        runtime: Runtime,
        role_profile: RoleProfile,
        observability: BoundObservability,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        plan_ref: str = "",
    ) -> None:
        self.runtime = runtime
        self.role_profile = role_profile
        self._observability = observability
        self.max_steps = max_steps
        self.max_wall_clock_seconds = max_wall_clock_seconds
        self._plan_ref = plan_ref

    @property
    def observability(self) -> BoundObservability:
        """组合注入的观测 backend（只读暴露，供组合根提升/复用）。"""
        return self._observability

    @property
    def plan_ref(self) -> str:
        """Immutable plan associated with this agent, if it was plan-bound."""
        return self._plan_ref

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result:
        text = _task_as_text(task)
        role = self.role_profile.role
        scope, top_level = adopt_run_scope(role=role)
        if ctx and ctx.session_id:
            set_session(ctx.session_id)
        bound_ctx = self._enrich_run_context(ctx)
        effective_wall = effective_agent_wall_clock(self.max_wall_clock_seconds)

        async def execute() -> Result:
            return await self.runtime.run(
                text,
                bound_ctx,
                max_steps=self.max_steps,
                max_wall_clock_seconds=effective_wall,
                agent_role=role,
            )

        with bind_backends(self._observability), run_scope(scope):
            if self._plan_ref:
                with plan_ref_scope(self._plan_ref):
                    return await self._run_lifecycle(
                        objective=text,
                        ctx=bound_ctx,
                        role=role,
                        top_level=top_level,
                        scope=scope,
                        execute=execute,
                    )
            return await self._run_lifecycle(
                objective=text,
                ctx=bound_ctx,
                role=role,
                top_level=top_level,
                scope=scope,
                execute=execute,
            )

    async def _run_lifecycle(
        self,
        *,
        objective: str,
        ctx: RunContext | None,
        role: str,
        top_level: bool,
        scope: RunScope,
        execute: Callable[[], Awaitable[Result]],
        resumed_snapshot: StateSnapshot | None = None,
    ) -> Result:
        """Record one fresh or resumed runtime invocation inside a RunScope.

        The lifecycle boundary remains kernel-owned rather than hook/plugin
        controlled: plugins may replace the ``Runtime`` through the profile,
        but must not omit the durable start/resume/finish facts that make its
        model-visible work and recovery path auditable.
        """
        # PR-3.1: spine envelope for the agent_loop.iteration execution point.
        from lca.plugins.events.publishers.spine_reflector_agent_spawn import (
            emit_agent_loop_iteration_end,
            emit_agent_loop_iteration_start,
        )

        iteration_kind = "resume" if resumed_snapshot is not None else "fresh"
        iteration_trace_id = scope.trace_id or (
            resumed_snapshot.trace_id if resumed_snapshot else ""
        )
        emit_agent_loop_iteration_start(
            trace_id=iteration_trace_id,
            role=role,
            iteration_kind=iteration_kind,
        )

        partial_token = begin_partial_buffer()
        record(
            AgentRunStarted(
                agent_role=role,
                strategy_key=_STRATEGY_KEY_SOLO if top_level else "",
                objective=objective,
                objective_preview=objective_preview(objective),
                from_role=ctx.from_role if ctx else "",
            )
        )
        if resumed_snapshot is not None:
            record_run_resumed(resumed_snapshot)
        finish_status = TaskStatus.CANCELED.value
        finish_output = ""
        finish_steps = 0
        finish_error = ""
        iteration_outcome: str = "success"
        try:
            result = await execute()
            self._stamp_resumable_snapshot(result, scope)
            finish_status = (
                result.status.value if isinstance(result.status, TaskStatus) else str(result.status)
            )
            finish_output = result.output or ""
            finish_steps = result.total_steps
            finish_error = result.error or ""
            return result
        except asyncio.CancelledError:
            finish_status = TaskStatus.CANCELED.value
            finish_output = drain_run_partial()
            finish_error = "canceled"
            iteration_outcome = "cancelled"
            raise
        except Exception as err:
            finish_status = TaskStatus.FAILED.value
            finish_output = drain_run_partial()
            finish_error = f"{type(err).__name__}: {err}"
            iteration_outcome = "failure"
            raise
        finally:
            record(
                AgentRunFinished(
                    status=finish_status,
                    output_text=finish_output,
                    steps=finish_steps,
                    error=finish_error,
                )
            )
            reset_partial_buffer(partial_token)
            emit_agent_loop_iteration_end(
                trace_id=iteration_trace_id,
                role=role,
                iteration_kind=iteration_kind,
                outcome=iteration_outcome,  # type: ignore[arg-type]
            )

    @staticmethod
    def _stamp_resumable_snapshot(result: Result, scope: RunScope) -> None:
        """Persist the owning RunScope on a pause checkpoint for later resume."""
        snapshot = result.extra.get("state_snapshot")
        if isinstance(snapshot, StateSnapshot):
            snapshot.trace_id = scope.trace_id
            snapshot.run_id = scope.run_id

    async def resume(
        self,
        snapshot: StateSnapshot,
        input: str | AgentMessage | None = None,
    ) -> Result:
        """Resume through the same observability and lifecycle boundary as ``run``."""
        msg = None
        if isinstance(input, AgentMessage):
            msg = input
        elif isinstance(input, str):
            msg = agent_message_text(input)

        role = self.role_profile.role
        scope, top_level = adopt_run_scope(
            role=role,
            trace_id=snapshot.trace_id or None,
            parent_run_id=snapshot.run_id or None,
        )

        async def execute() -> Result:
            return await self.runtime.resume(snapshot, input=msg, max_steps=self.max_steps)

        objective = f"resume:{snapshot.snapshot_id}"
        with bind_backends(self._observability), run_scope(scope):
            if self._plan_ref:
                with plan_ref_scope(self._plan_ref):
                    return await self._run_lifecycle(
                        objective=objective,
                        ctx=None,
                        role=role,
                        top_level=top_level,
                        scope=scope,
                        execute=execute,
                        resumed_snapshot=snapshot,
                    )
            return await self._run_lifecycle(
                objective=objective,
                ctx=None,
                role=role,
                top_level=top_level,
                scope=scope,
                execute=execute,
                resumed_snapshot=snapshot,
            )

    async def cancel(self) -> None:
        return None

    @staticmethod
    def _enrich_run_context(ctx: RunContext | None) -> RunContext | None:
        workspace = get_run_workspace()
        if workspace is None or workspace.deadline is None:
            return ctx
        if ctx is not None and ctx.deadline is not None:
            return ctx
        if ctx is None:
            return RunContext(deadline=workspace.deadline)
        return RunContext(
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
            from_role=ctx.from_role,
            context_refs=list(ctx.context_refs),
            deadline=workspace.deadline,
            team_awareness=ctx.team_awareness,
            extra=dict(ctx.extra),
        )

    def register_hook(self, hook_name: str, hook_fn: Hook) -> None:
        runtime = self.runtime
        if isinstance(runtime, HasHooks):
            runtime.hooks.register(hook_name, hook_fn)
