"""ADR-0075 的薄运行 façade。

``CognitiveRuntime`` 只负责创建初始 ``AgentState`` 并把运行委托给已验证的
声明式 driver。认知顺序、控制策略、暂停、恢复和外部 effect 均不得在此层按
业务身份分派。
"""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.atoms.enums import HookEvent
from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS, create_budget
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.protocols import (
    Body,
    Brain,
    MemorySystem,
    PerceiveHub,
    Reducer,
    Runtime,
    StateStore,
    StopRule,
)
from lca.contracts.protocols.declarative_phase_graph import DeclarativeValidationError
from lca.contracts.protocols.plan import CompiledRunPlan
from lca.layer0_infra.observability import get_span_context
from lca.layer2_runtime.declarative_runtime import (
    DeclarativeCheckpoint,
    DeclarativeRuntimeDriver,
    RuntimePhaseCapabilities,
)
from lca.layer2_runtime.reducer import DefaultReducer


class CognitiveRuntime(Runtime):
    """仅创建状态并委托已绑定的声明式运行计划。"""

    def __init__(
        self,
        brain: Brain,
        body: Body,
        memory: MemorySystem,
        hooks: HookRegistry,
        state_store: StateStore,
        stop_rule: StopRule,
        perceive_hub: PerceiveHub,
        *,
        reducer: Reducer | None = None,
        compiled_plan: CompiledRunPlan | None = None,
        phase_executors: Mapping[str, object] | None = None,
        effect_handlers: Mapping[str, object] | None = None,
    ) -> None:
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.state_store = state_store
        self.stop_rule = stop_rule
        self.perceive_hub = perceive_hub
        self.reducer: Reducer = reducer if reducer is not None else DefaultReducer()
        self.compiled_plan = compiled_plan
        self.phase_executors = dict(phase_executors or {})
        self.effect_handlers = dict(effect_handlers or {})

    async def run(
        self,
        task: str,
        ctx: RunContext | None = None,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        agent_role: str = "",
    ) -> Result:
        span_ctx = get_span_context()
        trace_id = (
            (ctx.trace_id if ctx and ctx.trace_id else None) or span_ctx.trace_id or new_id("trace")
        )
        state = self._new_state(
            task,
            trace_id=trace_id,
            ctx=ctx,
            max_steps=max_steps,
            max_wall_clock_seconds=max_wall_clock_seconds,
            agent_role=agent_role,
        )
        await self.hooks.trigger(HookEvent.ON_START.value, state)
        return await self._driver().execute(state)

    async def resume(
        self,
        checkpoint: DeclarativeCheckpoint,
        input: object | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> Result:
        del max_steps
        if not isinstance(checkpoint, DeclarativeCheckpoint):
            raise DeclarativeValidationError(
                "RT-004",
                "resume requires a DeclarativeCheckpoint with plan-bound phase cursor",
            )
        return await self._driver().resume_from_checkpoint(checkpoint, input=input)

    def _driver(self) -> DeclarativeRuntimeDriver:
        if self.compiled_plan is None or not self.compiled_plan.is_declarative:
            raise DeclarativeValidationError(
                "PG-001", "runtime requires a valid declarative CompiledRunPlan"
            )
        if not self.phase_executors:
            raise DeclarativeValidationError(
                "PS-002", "runtime requires plan-bound declarative phase executors"
            )
        self.compiled_plan.validation_report.require_valid()
        return DeclarativeRuntimeDriver(
            plan=self.compiled_plan,
            phase_executors=self.phase_executors,
            capabilities=RuntimePhaseCapabilities(
                brain=self.brain,
                body=self.body,
                memory=self.memory,
                perceive_hub=self.perceive_hub,
                stop_rule=self.stop_rule,
            ),
            reducer=self.reducer,
            hooks=self.hooks,
            state_store=self.state_store,
            effect_handlers=self.effect_handlers,
        )

    @staticmethod
    def _new_state(
        task: str,
        *,
        trace_id: str,
        ctx: RunContext | None,
        max_steps: int,
        max_wall_clock_seconds: int | None,
        agent_role: str,
    ) -> AgentState:
        state = AgentState(
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
        return state


__all__ = ["CognitiveRuntime"]
