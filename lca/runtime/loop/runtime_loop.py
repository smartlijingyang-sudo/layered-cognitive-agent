"""The narrow runtime entry for one verified declarative binding.

``CognitiveRuntime`` only creates fresh state and restores checkpoints. Plan
interpretation, capability selection, effect and delta dispatch, Journal, and
terminal projection all belong to ``DeclarativeRuntimeBindings`` and its
per-Turn drivers.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.infrastructure.observability.spine.event.record import Outcome

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.conversation import PRIOR_CONVERSATION_WM_KEY
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.policy.budget import DEFAULT_MAX_STEPS, create_budget
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import StateSnapshot
from lca.contracts.models.team.run.context import RunContext
from lca.contracts.observability import exc_to_record
from lca.contracts.protocols.runtime.runtime.lifecycle import RuntimeLifecycleEventType
from lca.contracts.protocols.runtime.runtime.runtime import Runtime
from lca.infrastructure.observability import get_current_run_scope, get_span_context
from lca.infrastructure.observability.spine.exception.emit import emit_exception_caught
from lca.runtime.loop.runtime_lifecycle_emitter import (
    RuntimeLifecycleEmitter,
    _event_type_for_result,
    _journal_sequence_from_result,
    _phase_cursor_from_result,
)
from lca.runtime.support.checkpoint_resolution import DeclarativeCheckpoint
from lca.runtime.support.runtime_bindings import DeclarativeRuntimeBindings

if TYPE_CHECKING:
    from lca.contracts.mechanisms import HookRegistry
    from lca.contracts.protocols import (
        ArtifactClosure,
        Body,
        Brain,
        MemorySystem,
        PerceiveHub,
        Reducer,
        StateStore,
    )
    from lca.contracts.protocols.act.effect.handler import EffectHandlerRegistry
    from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
        PhaseExecutor,
    )
    from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
    from lca.contracts.protocols.session.resume.input import ResumeInputAdapter
    from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
    from lca.contracts.protocols.state.plan import CompiledRunPlan
    from lca.harness.declarative.lifecycle.phase_observation import PhaseObserver


class CognitiveRuntime(Runtime):
    """A narrow run entry backed by one verified declarative dependency closure.

    The constructor accepts one immutable binding. Common runtime capabilities
    remain available through read-only properties for existing Agents and tests,
    while all selection and Turn-level lifecycle ownership stays in the binding.
    """

    def __init__(self, bindings: DeclarativeRuntimeBindings) -> None:
        self._bindings = bindings
        self._lifecycle = RuntimeLifecycleEmitter(bindings)

    @property
    def bindings(self) -> DeclarativeRuntimeBindings:
        """Return the sole verified declarative binding for this runtime."""

        return self._bindings

    @property
    def brain(self) -> Brain:
        return self._bindings.capabilities.brain

    @property
    def body(self) -> Body:
        return self._bindings.capabilities.body

    @property
    def memory(self) -> MemorySystem:
        return self._bindings.capabilities.memory

    @property
    def hooks(self) -> HookRegistry:
        return self._bindings.hooks

    @property
    def state_store(self) -> StateStore:
        return self._bindings.state_store

    @property
    def perceive_hub(self) -> PerceiveHub:
        return self._bindings.capabilities.perceive_hub

    @property
    def reducer(self) -> Reducer:
        return self._bindings.reducer

    @property
    def compiled_plan(self) -> CompiledRunPlan | None:
        return self._bindings.plan

    @property
    def phase_executors(self) -> Mapping[str, PhaseExecutor]:
        return self._bindings.phase_executors

    @property
    def effect_handler_registry(self) -> EffectHandlerRegistry:
        return self._bindings.effect_handler_registry

    @property
    def delta_handler_registry(self) -> DeltaHandlerRegistry:
        return self._bindings.delta_handler_registry

    @property
    def artifact_closure(self) -> ArtifactClosure:
        return self._bindings.artifact_closure

    @property
    def idempotency_store(self) -> IdempotencyStore:
        return self._bindings.idempotency_store

    @property
    def resume_input_adapter(self) -> ResumeInputAdapter:
        return self._bindings.resume_input_adapter

    @property
    def phase_observer(self) -> PhaseObserver:
        """Expose the profile-selected read-only observer without reselecting it."""

        return self._bindings.phase_observer

    async def run(
        self,
        task: str,
        ctx: RunContext | None = None,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        agent_role: str = "",
    ) -> Result:
        """Create fresh state and delegate it to the binding's Turn path."""

        span_ctx = get_span_context()
        run_scope = get_current_run_scope()
        scope_trace_id = run_scope.trace_id if run_scope and run_scope.trace_id else None
        trace_id = (
            (ctx.trace_id if ctx and ctx.trace_id else None)
            or scope_trace_id
            or span_ctx.trace_id
            or new_id("trace")
        )
        state = self._bindings.new_state(
            trace_id=trace_id,
            task=task,
            budget=create_budget(
                max_steps=max_steps,
                max_wall_clock_seconds=max_wall_clock_seconds,
            ),
            agent_role=agent_role,
            from_role=(ctx.from_role if ctx else ""),
            team_awareness=(ctx.team_awareness if ctx else None),
        )
        if ctx and ctx.extra.get(PRIOR_CONVERSATION_WM_KEY):
            state.extra[PRIOR_CONVERSATION_WM_KEY] = ctx.extra[PRIOR_CONVERSATION_WM_KEY]
        self._bindings.require_executable_plan()
        from lca.infrastructure.session.emit.lifecycle_emit import (
            accept_user_message,
            begin_turn,
            reset_lifecycle,
        )
        # PR-E:把 reducer 装到 SkillActivationReducerBridge,让
        # ``register_activated`` 把激活 fold 进 state.activated_skills
        # (C4 兑现路径)。dispose 由 finally 兜底,保证 run 中断不悬空。
        from lca.infrastructure.skills.activation.bridge import SkillActivationReducerBridge

        bridge: SkillActivationReducerBridge = SkillActivationReducerBridge()
        # 进程级 singleton —— install 一次覆盖前一个 run 的绑定
        # (若前一个 run 忘记 dispose,这里强制清理)。
        from lca.infrastructure.skills.activation.bridge import bridge as global_bridge

        # 持有 live state 的 closure;``state`` 是 mutable,reducer 内
        # ``extend`` 会改 list 本身 —— 不需要 reassign 引用。
        live_state = state
        global_bridge.install(
            reducer=self.reducer,
            state_getter=lambda: live_state,
        )
        try:
            reset_lifecycle()
            begin_turn()
            accept_user_message(message_id=f"task:{trace_id}", content=task)
            await self._lifecycle.publish(RuntimeLifecycleEventType.STARTED, state)
            return await self._run_driver(
                state, runner=lambda: self._bindings.new_driver().run(state)
            )
        finally:
            global_bridge.dispose()

    async def _publish_terminal_event(self, state: object, result: Result) -> None:
        """Compatibility seam delegating terminal projection to the lifecycle emitter."""
        await self._lifecycle.publish_terminal(state, result)

    async def resume(
        self,
        snapshot: StateSnapshot,
        input: object | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> Result:
        """Restore state, fold normalized input facts, then use the same Turn path."""

        del max_steps
        state = await self.state_store.load(snapshot.state_ref)
        resume_input = self.resume_input_adapter.normalize(input)
        state = self.reducer.apply_resume(
            state,
            resume_input.input_value,
            resume_input.turn,
        )
        from lca.infrastructure.session._overflow_0.bindings import resolve_session_reader
        from lca.infrastructure.session.emit.surface_emit import append_human_answer_surface

        session_reader = resolve_session_reader()
        if session_reader is not None and resume_input.turn is not None:
            obs = resume_input.turn.observation
            if obs is not None and (obs.extra or {}).get("source") == "human_answer":
                payload = obs.payload
                if isinstance(payload, str):
                    append_human_answer_surface(payload)

        phase_cursor = snapshot.phase_cursor
        if phase_cursor is None:
            phase_cursor = getattr(state, "phase_cursor", None)
        self._bindings.require_executable_plan()
        if phase_cursor is None:
            raise ValueError(
                "CognitiveRuntime.resume requires a declarative phase_cursor. "
                "Legacy runtime loop has been removed (ADR-0074/0075 declarative cutover)."
            )

        checkpoint = DeclarativeCheckpoint(
            state_snapshot=snapshot,
            cursor=phase_cursor,
            plan_ref=phase_cursor.plan_ref,
            resume_state=state,
        )
        # PR-3.4: bracket the resumed Turn with runtime.resume.start and
        # runtime.resume.end. The start event fires after the checkpoint is
        # materialised so the event payload reflects the plan_ref / node_id
        # the driver is about to interpret. The end event is emitted from
        # inside _run_driver's exception/finally envelope.
        from lca.infrastructure.session.emit.runtime_emit import emit_runtime_resume_start

        emit_runtime_resume_start(
            plan_ref=phase_cursor.plan_ref,
            state_ref=snapshot.state_ref,
            node_id=phase_cursor.node_id,
        )
        await self._lifecycle.publish(
            RuntimeLifecycleEventType.RESUMED,
            state,
            phase_cursor=phase_cursor.node_id,
        )
        return await self._run_driver(
            state,
            runner=lambda: self._bindings.new_driver().resume(checkpoint),
            phase_cursor=phase_cursor.node_id,
            resume_envelope=True,
        )

    async def _run_driver(
        self,
        state: object,
        *,
        runner: Callable[[], Awaitable[Result]],
        phase_cursor: str | None = None,
        resume_envelope: bool = False,
    ) -> Result:
        """Own driver lifecycle projection for both fresh and resumed turns."""
        # PR-3.4: capture the resume envelope metadata so we can emit
        # ``runtime.resume.end`` after the driver returns or raises.
        resume_envelope_meta: dict[str, str] | None = None
        if resume_envelope and phase_cursor is not None:
            resume_envelope_meta = {
                "plan_ref": self._bindings.plan_ref(),
                "state_ref": (
                    getattr(state, "snapshot_state_ref", "") or getattr(state, "state_ref", "")
                ),
                "node_id": phase_cursor,
            }
        from lca.infrastructure.session.emit.runtime_emit import (
            emit_exception_finally,
            emit_lifecycle_finally,
            emit_runtime_resume_end,
        )

        trace_id = str(getattr(state, "trace_id", ""))
        boundary = "resume" if resume_envelope else "terminal_driver"
        run_scope = get_current_run_scope()
        run_id = str(run_scope.run_id if run_scope is not None else "")

        def _emit_caught(exc: BaseException) -> None:
            # ADR-0169 SSOT: normalize the real exception instance before the
            # single emitter; 4-key dict payloads drop traceback evidence.
            record = exc_to_record(
                exc,
                boundary=boundary,
                run_id=run_id,
                trace_id=trace_id,
            )
            emit_exception_caught(record)

        # Mutable holder so the except branches can update the outcome
        # that the finally block reads when emitting resume.end / finally.
        outcome_holder: dict[str, Outcome] = {"value": "success"}
        from lca.infrastructure.session._overflow_0.bindings import await_step_boundary_checkpoint

        await await_step_boundary_checkpoint()
        try:
            result = await runner()
        except asyncio.CancelledError as exc:
            await self._lifecycle.publish(
                RuntimeLifecycleEventType.CANCELED,
                state,
                status=TaskStatus.CANCELED,
                phase_cursor=phase_cursor,
            )
            _emit_caught(exc)
            outcome_holder["value"] = "cancelled"
            raise
        except Exception as exc:
            await self._lifecycle.publish(
                RuntimeLifecycleEventType.FAILED,
                state,
                status=TaskStatus.FAILED,
                phase_cursor=phase_cursor,
            )
            _emit_caught(exc)
            outcome_holder["value"] = "failure"
            raise
        finally:
            if resume_envelope_meta is not None:
                emit_runtime_resume_end(
                    plan_ref=resume_envelope_meta["plan_ref"],
                    state_ref=resume_envelope_meta["state_ref"],
                    node_id=resume_envelope_meta["node_id"],
                    outcome=outcome_holder["value"],
                )
            # ADR-0166 S5: 异常路径走 exception.finally；正常路径走
            # lifecycle.finally —— reader 不再被「成功也发 exception.*」混淆。
            if outcome_holder["value"] == "success":
                emit_lifecycle_finally(boundary=boundary, trace_id=trace_id)
            else:
                emit_exception_finally(
                    boundary=boundary,
                    trace_id=trace_id,
                    outcome=outcome_holder["value"],
                )
        await self._lifecycle.publish_terminal(state, result)
        from lca.infrastructure.session.emit.lifecycle_emit import (
            checkpoint,
            emit_approval_pause_from_result,
            end_turn,
            terminal_checkpoint_status,
        )

        if result.status is TaskStatus.INPUT_REQUIRED:
            emit_approval_pause_from_result(result)
        else:
            terminal_status = terminal_checkpoint_status(result.status)
            if terminal_status is not None:
                checkpoint(terminal_status)
            end_turn(reason=result.status.value if hasattr(result.status, "value") else "completed")
        return result


__all__ = [
    "CognitiveRuntime",
    "_event_type_for_result",
    "_journal_sequence_from_result",
    "_phase_cursor_from_result",
]
