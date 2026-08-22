"""CognitiveRuntime —— 核心认知循环（ADR-0002 + ADR-0066）。

v3 闭环：
    Loop 只做编排：perceive → think → act → reflect → remember → stop。
    终止判定完全委托给 StopRule，业务逻辑零泄漏。

L2 层职责：
    将 Brain（认知）、Body（执行）、Memory（记忆）三大能力串联为可中断、
    可恢复、可观测的闭环。所有 state mutation 集中在 ``Reducer`` 协议
    实现（C4 兑现）；所有 phase hook 直接调 ``hooks.trigger``（删除原
    _emit / middleware_bag 中间层）。
"""

from __future__ import annotations

from collections.abc import Mapping

import structlog

from lca.contracts.atoms.enums import ActionType, HookEvent
from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS, create_budget
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState, StateSnapshot
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
from lca.contracts.protocols.plan import CompiledRunPlan
from lca.contracts.protocols.reducer import LoopTopology
from lca.layer0_infra.observability import get_span_context
from lca.layer2_runtime.loop_topology import ClosedSetTopology
from lca.layer2_runtime.reducer import DefaultReducer

_log = structlog.get_logger("lca.runtime_loop")


class CognitiveRuntime(Runtime):
    """核心认知循环实现（ADR-0002 + ADR-0066）。

    v3 §5.3: ``perceive_hub: PerceiveHub`` 必填。L2 只依赖 Protocol，
    生产 Composer 必须注入真正的 Hub；测试可用 ``NullPerceiveHub``。

    ADR-0066: state mutation 集中于 ``reducer`` 参数（默认
    ``DefaultReducer``）；phase hook 直接由 ``hooks.trigger`` 触发，
    不再经 ``_emit`` 中间层。
    """

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
        topology: LoopTopology | None = None,
        control_plan: ControlPlan | None = None,
        compiled_plan: CompiledRunPlan | None = None,
        phase_executors: Mapping[str, object] | None = None,
    ) -> None:
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.state_store = state_store
        self.stop_rule = stop_rule
        self.perceive_hub = perceive_hub
        self.reducer: Reducer = reducer if reducer is not None else DefaultReducer()
        self.topology: LoopTopology = topology if topology is not None else ClosedSetTopology()
        self.control_plan = control_plan
        self.compiled_plan = compiled_plan
        self.phase_executors = dict(phase_executors or {})

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
        state = AgentState(
            trace_id=trace_id,
            task=task,
            budget=create_budget(
                max_steps=max_steps, max_wall_clock_seconds=max_wall_clock_seconds
            ),
            agent_role=agent_role,
            from_role=(ctx.from_role if ctx else ""),
            team_awareness=(ctx.team_awareness if ctx else None),
        )
        if ctx and ctx.extra.get(PRIOR_CONVERSATION_WM_KEY):
            state.extra[PRIOR_CONVERSATION_WM_KEY] = ctx.extra[PRIOR_CONVERSATION_WM_KEY]
        await self.hooks.trigger(HookEvent.ON_START.value, state)
        if self.compiled_plan is None or not self.phase_executors:
            raise ValueError(
                "CognitiveRuntime requires a compiled_plan and phase_executors. "
                "Legacy runtime loop has been removed (ADR-0074/0075 declarative cutover)."
            )
        
        from lca.layer2_runtime.declarative_runtime import (
            DeclarativeRuntimeDriver,
            RuntimePhaseCapabilities,
        )

        return await DeclarativeRuntimeDriver(
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
        ).run(state)

    async def resume(
        self,
        snapshot: StateSnapshot,
        input: object | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> Result:
        state = await self.state_store.load(snapshot.state_ref)
        turn: Turn | None = None
        if input is not None:
            answer_text = input if isinstance(input, str) else str(input)
            answer_obs = Observation(
                observation_id=new_id("obs"),
                success=True,
                payload=answer_text,
                extra={"source": "human_answer", "tool_name": "askUserQuestion"},
            )
            answer_decision = Decision(
                decision_id=new_id("dec"),
                action_type=ActionType.ASK_HUMAN,
                rationale="Human-in-the-loop answer received.",
                confidence=1.0,
                tool_calls=[
                    ToolCall(call_id=new_id("tc"), tool_name="askUserQuestion", arguments={}),
                ],
            )
            turn = Turn(decision=answer_decision, observation=answer_obs)
        state = self.reducer.apply_resume(state, input, turn)
        
        # 检查是否有声明式 cursor，委托给 declarative driver
        phase_cursor = getattr(state, "phase_cursor", None)
        if phase_cursor is None or self.compiled_plan is None:
            raise ValueError(
                "CognitiveRuntime.resume requires a declarative phase_cursor and compiled_plan. "
                "Legacy runtime loop has been removed (ADR-0074/0075 declarative cutover)."
            )
        
        from lca.layer2_runtime.declarative_runtime import (
            DeclarativeCheckpoint,
            DeclarativeRuntimeDriver,
            RuntimePhaseCapabilities,
        )
        
        checkpoint = DeclarativeCheckpoint(
            state_snapshot=snapshot,
            cursor=phase_cursor,
            plan_ref=phase_cursor.plan_ref,
        )
        
        # 构建 phase executors 映射
        phase_executors = {}
        if self.phase_executors:
            phase_executors.update(self.phase_executors)
        
        capabilities = RuntimePhaseCapabilities(
            brain=self.brain,
            body=self.body,
            memory=self.memory,
            perceive_hub=self.perceive_hub,
            stop_rule=self.stop_rule,
        )
        
        return await DeclarativeRuntimeDriver(
            plan=self.compiled_plan,
            phase_executors=phase_executors,
            capabilities=capabilities,
            reducer=self.reducer,
            hooks=self.hooks,
        ).resume(checkpoint)


__all__ = ["CognitiveRuntime"]
