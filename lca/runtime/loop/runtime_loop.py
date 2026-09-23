"""The narrow runtime entry for one verified declarative binding.

``CognitiveRuntime`` only creates fresh state and restores checkpoints. Plan
interpretation, capability selection, effect and delta dispatch, Journal, and
terminal projection all belong to ``DeclarativeRuntimeBindings`` and its
per-Turn drivers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.infrastructure.observability.spine.event.record import Outcome

from lca.contracts.atoms.ids.ids import new_id
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
    from lca.application.vocal.runtime_wiring import RuntimeVocalContext
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
    from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
    from lca.contracts.protocols.session.resume.input import ResumeInputAdapter
    from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
    from lca.contracts.protocols.state.plan import CompiledRunPlan
    from lca.harness.declarative.lifecycle.phase_observation import PhaseObserver

logger = logging.getLogger(__name__)


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
        self._bindings.require_executable_plan()
        from lca.infrastructure.session.bindings import (
            resolve_session_reader,
        )
        from lca.infrastructure.session.emit.lifecycle_emit import (
            begin_turn,
            reset_lifecycle,
        )

        # PR-E:把 reducer 装到 SkillActivationReducerBridge,让
        # ``register_activated`` 把激活 fold 进 state.activated_skills
        # (C4 兑现路径)。dispose 由 finally 兜底,保证 run 中断不悬空。
        # 进程级 singleton —— install 一次覆盖前一个 run 的绑定
        # (若前一个 run 忘记 dispose,这里强制清理)。
        from lca.infrastructure.skills.activation.bridge import bridge as global_bridge
        from lca.runtime.session.run_session_writer import RunSessionWriter

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
            session_reader = resolve_session_reader()
            run_writer: RunSessionWriter | None = None
            if session_reader is not None:
                run_writer = RunSessionWriter(session=session_reader)
                # Layer the per-run writer into the phase capabilities so
                # think subgraph node executors (``history.derive``,
                # ``llm.call``) can read it via ``context.runtime.writer``;
                # otherwise their declared ``writer`` port fails the
                # port-required TypeError before any reasoning fires.
                if self._bindings.capabilities.get("writer") is None:
                    self._bindings = self._bindings.with_writer(run_writer)
                # ADR-0244: Seed prior conversation turns via Session single track
                prior_turns = ctx.prior_turns if ctx else ()
                if prior_turns:
                    run_writer.seed_prior_turns(prior_turns)
                run_writer.append_user_message(
                    message_id=f"task:{trace_id}",
                    role="user",
                    content=task,
                )
            # ADR-0248: 运行态声带与硬闸解析
            vocal_mode = None
            wake_source = "user_input"
            wake_context = None
            if ctx:
                vocal_mode = getattr(ctx, "vocal_mode", None) or (ctx.extra or {}).get("vocal_mode")
                wake_source = (ctx.extra or {}).get("wake_source", "user_input")
                wake_context = (ctx.extra or {}).get("wake_context")

            from lca.application.vocal.runtime_wiring import resolve_runtime_vocal
            from lca.contracts.models.vocal.models import VocalMode

            vocal_ctx = resolve_runtime_vocal(
                vocal_mode=vocal_mode,
                operation_id=trace_id,
                wake_source=wake_source,
                wake_context=wake_context,
            )
            if vocal_ctx.mode == VocalMode.GATED:
                self._bindings = self._bindings.with_vocal_gate(vocal_ctx.gate)

            await self._lifecycle.publish(RuntimeLifecycleEventType.STARTED, state)
            return await self._run_driver(
                state,
                runner=lambda: self._bindings.new_driver().run(state),
                vocal_ctx=vocal_ctx,
                ctx=ctx,
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
        # ADR-0246 PR-8: 恢复路径补跑记忆捕获——人工回答也是用户陈述，
        # 先提炼身份/偏好再进入下一轮，避免「说了但没记」。
        await self._capture_resume_memory(state, resume_input)
        from lca.infrastructure.session.bindings import resolve_session_reader
        from lca.runtime.session.run_session_writer import RunSessionWriter

        session_reader = resolve_session_reader()
        if session_reader is not None and resume_input.turn is not None:
            obs = resume_input.turn.observation
            if obs is not None and (obs.extra or {}).get("source") == "human_answer":
                payload = obs.payload
                if isinstance(payload, str):
                    stripped = payload.strip()
                    if stripped:
                        RunSessionWriter(session=session_reader).append_user_message(
                            message_id=f"human_answer:{obs.observation_id}",
                            role="human",
                            content=stripped,
                        )

        phase_cursor = snapshot.phase_cursor
        if phase_cursor is None:
            phase_cursor = getattr(state, "phase_cursor", None)
        self._bindings.require_executable_plan()
        if phase_cursor is None:
            raise ValueError(
                "CognitiveRuntime.resume requires a declarative phase_cursor. "
                "Legacy runtime loop has been removed (ADR-0074/0075 declarative cutover)."
            )

        # ``StateSnapshot.phase_cursor`` is the declarative_1 shape
        # (``node_id`` + visit counts); ``DeclarativeCheckpoint`` declares
        # the adapter shape (``current_node_id`` + visited nodes). Project
        # here — the violator — instead of teaching every consumer both.
        # A resumed pause restarts the turn (visited budgets reset; the
        # terminated pre-pause traversal must not constrain the new one).
        from lca.framework.graph.adapter import PhaseRunCursor as _AdapterCursor

        adapter_cursor = _AdapterCursor(
            current_node_id=str(getattr(phase_cursor, "node_id", "")),
            visited_nodes=(),
        )
        if not adapter_cursor.current_node_id:
            raise ValueError("resume cursor must carry a node_id to re-enter at")

        checkpoint = DeclarativeCheckpoint(
            state_snapshot=snapshot,
            cursor=adapter_cursor,
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

    async def _capture_resume_memory(self, state: object, resume_input: object) -> None:
        """补跑记忆捕获：人工回答 → LLM 蒸馏 → memory.update（ADR-0246 PR-8）。

        必须严格满足 fail-soft 原则：记忆提炼属于旁路增强，任何异常（如
        能力缺失、LLM 蒸馏异常、存储异常）均不得阻断恢复主流程。
        """
        from lca.runtime.support.resume_memory import capture_resume_memory

        try:
            memory = self._bindings.capabilities.get("memory")
            adapter = self._bindings.capabilities.get("adapter")
            await capture_resume_memory(memory, adapter, resume_input, state)
        except Exception:
            # 记忆捕获失败绝对不阻断恢复主流程（fail-soft）
            logger.debug("Failed to capture resume memory (fail-soft)", exc_info=True)

    async def _run_driver(
        self,
        state: object,
        *,
        runner: Callable[[], Awaitable[Result]],
        phase_cursor: str | None = None,
        resume_envelope: bool = False,
        vocal_ctx: RuntimeVocalContext | None = None,
        ctx: RunContext | None = None,
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
        from lca.infrastructure.session.bindings import await_step_boundary_checkpoint

        await await_step_boundary_checkpoint()
        try:
            result = await runner()
            # ADR-0248: 门控声带轮次结算核验硬闸
            if vocal_ctx is not None and vocal_ctx.settle_guard is not None:
                vocal_ctx.settle_guard.validate_turn_settle()
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
            if outcome_holder["value"] == "success" and ctx is not None:
                features = (ctx.extra or {}).get("transcript_features")
                if features:
                    from lca.application.initiative.hooks import evaluate_initiative

                    offer = evaluate_initiative(features)
                    if offer is not None:
                        # initiative_offer 是运行时派生投影，写入 Result.extra 而非回写
                        # 输入契约 RunContext.extra（RunContext 是只读输入，不是输出总线）。
                        result.extra["initiative_offer"] = offer.model_dump()
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
            end_turn,
            terminal_checkpoint_status,
        )

        # Pause facts (approval.persisted + waiting_input checkpoint)
        # are written by RuntimeResultFinalizer during finalize on this
        # same Result; emitting here as well double-appends the pair.
        if result.status is not TaskStatus.INPUT_REQUIRED:
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
