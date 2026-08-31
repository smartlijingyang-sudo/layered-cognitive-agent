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

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS, create_budget
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import StateSnapshot
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols.runtime.runtime import Runtime
from lca.contracts.protocols.runtime.runtime_lifecycle import RuntimeLifecycleEventType
from lca.infrastructure.observability import get_current_run_scope, get_span_context
from lca.runtime.checkpoint_resolution import DeclarativeCheckpoint
from lca.runtime.runtime_bindings import DeclarativeRuntimeBindings
from lca.runtime.runtime_lifecycle_emitter import (
    RuntimeLifecycleEmitter,
    _event_type_for_result,
    _journal_sequence_from_result,
    _phase_cursor_from_result,
)

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
    from lca.contracts.protocols.act.effect_handler import EffectHandlerRegistry
    from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseExecutor
    from lca.contracts.protocols.journal.idempotency import IdempotencyStore
    from lca.contracts.protocols.session.resume_input import ResumeInputAdapter
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
        await self._lifecycle.publish(RuntimeLifecycleEventType.STARTED, state)
        await self.hooks.trigger(HookEvent.ON_START.value, state)
        return await self._run_driver(state, runner=lambda: self._bindings.new_driver().run(state))

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
        await self._lifecycle.publish(
            RuntimeLifecycleEventType.RESUMED,
            state,
            phase_cursor=phase_cursor.node_id,
        )
        return await self._run_driver(
            state,
            runner=lambda: self._bindings.new_driver().resume(checkpoint),
            phase_cursor=phase_cursor.node_id,
        )

    async def _run_driver(
        self,
        state: object,
        *,
        runner: Callable[[], Awaitable[Result]],
        phase_cursor: str | None = None,
    ) -> Result:
        """Own driver lifecycle projection for both fresh and resumed turns."""
        lifecycle_context = {"phase_cursor": phase_cursor} if phase_cursor else {}
        try:
            result = await runner()
        except asyncio.CancelledError:
            await self._lifecycle.publish(
                RuntimeLifecycleEventType.CANCELED,
                state,
                status=TaskStatus.CANCELED,
                **lifecycle_context,
            )
            raise
        except Exception:
            await self._lifecycle.publish(
                RuntimeLifecycleEventType.FAILED,
                state,
                status=TaskStatus.FAILED,
                **lifecycle_context,
            )
            raise
        await self._lifecycle.publish_terminal(state, result)
        return result


__all__ = [
    "CognitiveRuntime",
    "_event_type_for_result",
    "_journal_sequence_from_result",
    "_phase_cursor_from_result",
]
