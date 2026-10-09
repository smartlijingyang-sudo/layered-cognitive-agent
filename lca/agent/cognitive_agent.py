"""CognitiveAgent — single agent runtime unit."""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import replace

from lca.agent.run_envelope import (
    EnvelopeSpec,
    RunEventSessionBinder,
    TranslatedOutcome,
    run_envelope,
)
from lca.contracts.mechanisms import Hook
from lca.contracts.models.core.conversation.message import (
    AgentMessage,
    agent_message_as_text,
    agent_message_text,
)
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.policy.budget import DEFAULT_MAX_STEPS
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import StateSnapshot
from lca.contracts.models.observability.journal.journal import (
    AgentRunFinished,
    AgentRunStarted,
    RunScope,
)
from lca.contracts.models.observability.plan.ref import plan_ref_scope
from lca.contracts.models.team.partial.buffer import (
    begin_partial_buffer,
    drain_run_partial,
    reset_partial_buffer,
)
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.run.context import RunContext
from lca.contracts.protocols import AgentUnit, Runtime
from lca.contracts.protocols.graph.errors import LoopObligationExceededError
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
from lca.runtime.loop.runtime_lifecycle import record_run_resumed

_STRATEGY_KEY_SOLO = "solo"


def _task_as_text(task: str | AgentMessage) -> str:
    if isinstance(task, AgentMessage):
        return agent_message_as_text(task)
    return task


def _loop_obligation_failed_result(
    err: LoopObligationExceededError,
    *,
    scope: RunScope,
    partial_output: str,
) -> Result:
    """Translate a non-converging graph run into a fail-closed Result.

    Preserves the mechanism facts (plan / edge / bound / taken iterations)
    on ``Result.error`` and ``Result.extra`` instead of swallowing them.
    ``Result.budget_used`` stays the zero Budget per the Result contract
    ("non-COMPLETED runs carry the zero Budget").
    """
    result = Result.failed(f"{type(err).__name__}: {err}")
    result.trace_id = scope.trace_id or ""
    result.total_steps = err.taken or 0
    result.output = partial_output or None
    result.extra["loop_obligation"] = {
        "plan_id": err.plan_id,
        "edge": {"source": err.source, "target": err.target},
        "max_iterations": err.max_iterations,
        "taken": err.taken,
    }
    return result


def _agent_translate_success(result: Result) -> TranslatedOutcome:
    """Agent flavor of execute() success: finish facts mirror the Result."""
    return TranslatedOutcome(
        status=result.status.value if isinstance(result.status, TaskStatus) else str(result.status),
        output=result.output or "",
        steps=result.total_steps,
        error=result.error or "",
        outcome="success",
        disposition="return",
        result=result,
    )


def _agent_translate_cancelled() -> TranslatedOutcome:
    """Agent flavor of CancelledError: partial output drained, outcome 'cancelled'."""
    return TranslatedOutcome(
        status=TaskStatus.CANCELED.value,
        output=drain_run_partial(),
        steps=0,
        error="canceled",
        outcome="cancelled",
        disposition="raise",
    )


def _agent_translate_loop_obligation(
    err: LoopObligationExceededError, *, scope: RunScope
) -> TranslatedOutcome:
    """Agent flavor of non-convergence: fail-closed failed Result (RA-023)."""
    partial_output = drain_run_partial()
    return TranslatedOutcome(
        status=TaskStatus.FAILED.value,
        output=partial_output,
        steps=0,
        error=f"{type(err).__name__}: {err}",
        outcome="failure",
        disposition="return",
        result=_loop_obligation_failed_result(
            err, scope=scope, partial_output=partial_output
        ),
    )


def _agent_translate_error(err: Exception) -> TranslatedOutcome:
    """Agent flavor of unexpected error: fail-loud, partial output drained."""
    return TranslatedOutcome(
        status=TaskStatus.FAILED.value,
        output=drain_run_partial(),
        steps=0,
        error=f"{type(err).__name__}: {err}",
        outcome="failure",
        disposition="raise",
    )


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
        event_session_binder: RunEventSessionBinder | None = None,
    ) -> None:
        self.runtime = runtime
        self.role_profile = role_profile
        self._observability = observability
        self.max_steps = max_steps
        self.max_wall_clock_seconds = max_wall_clock_seconds
        self._plan_ref = plan_ref
        # Composition-injected ADR-0186 run binder; None → publish fail-loud.
        self._event_session_binder = event_session_binder

    @property
    def observability(self) -> BoundObservability:
        """组合注入的观测 backend（只读暴露，供组合根提升/复用）。"""
        return self._observability

    @property
    def plan_ref(self) -> str:
        """Immutable plan associated with this agent, if it was plan-bound."""
        return self._plan_ref

    @property
    def event_session_binder(self) -> RunEventSessionBinder | None:
        """Optional run-boundary Session binder from composition root."""
        return self._event_session_binder

    async def run(
        self,
        task: str | AgentMessage,
        ctx: RunContext | None = None,
    ) -> Result:
        # RA-046: fail loud at the entry — a None task used to travel deep
        # into the runtime and die with an obscure TypeError inside
        # objective_preview (None[:N]).
        if task is None:
            raise TypeError("Agent.run() task must be str | AgentMessage, got None")
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
        iteration_kind = "resume" if resumed_snapshot is not None else "fresh"
        iteration_trace_id = scope.trace_id or (
            resumed_snapshot.trace_id if resumed_snapshot else ""
        )

        binder = self._event_session_binder
        bound_cm = (
            binder.bound(scope.run_id)
            if binder is not None
            else contextlib.nullcontext()
        )

        with bound_cm:
            return await self._run_lifecycle_body(
                objective=objective,
                ctx=ctx,
                role=role,
                top_level=top_level,
                scope=scope,
                execute=execute,
                resumed_snapshot=resumed_snapshot,
                iteration_kind=iteration_kind,
                iteration_trace_id=iteration_trace_id,
            )

    async def _run_lifecycle_body(
        self,
        *,
        objective: str,
        ctx: RunContext | None,
        role: str,
        top_level: bool,
        scope: RunScope,
        execute: Callable[[], Awaitable[Result]],
        resumed_snapshot: StateSnapshot | None = None,
        iteration_kind: str,
        iteration_trace_id: str,
    ) -> Result:
        """Emit + execute inside an already-bound (or intentionally unbound) Session.

        Iteration envelope converged with TeamHandle (RA-082): the agent only
        supplies its Started/Finished factories, resume hook, partial-buffer
        section and outcome translations; the try/except/finally cascade lives
        in lca.agent.run_envelope.run_envelope.
        """
        # PR-3.1: spine envelope for the agent_loop.iteration execution point.
        from lca.infrastructure.session.bindings import active_publish_session

        # 热路径 cheap 检查(todo-38,2026-10-05 裁决):本函数 docstring 允许
        # “intentionally unbound”,无 Session 时跳过,不抛 RuntimeError。
        has_session = active_publish_session() is not None

        def emit_started() -> None:
            if has_session:
                record(
                    AgentRunStarted(
                        agent_role=role,
                        strategy_key=_STRATEGY_KEY_SOLO if top_level else "",
                        objective=objective,
                        objective_preview=objective_preview(objective),
                        from_role=ctx.from_role if ctx else "",
                    )
                )

        def emit_resumed() -> None:
            if resumed_snapshot is not None and has_session:
                record_run_resumed(resumed_snapshot)

        def emit_finished(status: str, output: str, steps: int, error: str) -> None:
            # 热路径 cheap 检查(todo-38,2026-10-05 裁决):ContextVar 按上下文隔离,每次现查。
            if active_publish_session() is not None:
                record(
                    AgentRunFinished(
                        status=status,
                        output_text=output,
                        steps=steps,
                        error=error,
                    )
                )

        def translate_success(result: Result) -> TranslatedOutcome:
            self._stamp_resumable_snapshot(result, scope)
            return _agent_translate_success(result)

        spec = EnvelopeSpec(
            iteration_kind=iteration_kind,
            trace_id=iteration_trace_id,
            role=role,
            begin_section=begin_partial_buffer,
            emit_started=emit_started,
            emit_resumed=emit_resumed,
            translate_success=translate_success,
            translate_cancelled=_agent_translate_cancelled,
            translate_loop_obligation=lambda err: _agent_translate_loop_obligation(
                err, scope=scope
            ),
            translate_error=_agent_translate_error,
            emit_finished=emit_finished,
            end_section=reset_partial_buffer,
        )
        return await run_envelope(spec=spec, execute=execute)

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
        # dataclasses.replace: future RunContext fields ride along instead of
        # being silently dropped. The defensive copies are kept — naive
        # replace would alias context_refs/extra and change downstream
        # mutation behavior.
        return replace(
            ctx,
            deadline=workspace.deadline,
            context_refs=list(ctx.context_refs),
            extra=dict(ctx.extra),
        )

    def register_hook(self, hook_name: str, hook_fn: Hook) -> None:
        runtime = self.runtime
        if isinstance(runtime, HasHooks):
            runtime.hooks.register(hook_name, hook_fn)
