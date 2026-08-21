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

import structlog

from lca.contracts.atoms.enums import ActionType, HookEvent, SnapshotReason
from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS, create_budget
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import ApprovalPendingError, BudgetExceededError, Result
from lca.contracts.models.core.state import AgentState, StateSnapshot
from lca.contracts.models.core.stop import StopReason
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
from lca.contracts.protocols.reducer import LoopTopology
from lca.layer0_infra.observability import get_span_context
from lca.layer0_infra.skills.activation_scope import get_newly_activated
from lca.layer2_runtime.completion.artifact_closure import synthesize_artifact_closure
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
        return await self._loop(state, max_steps)

    async def resume(
        self,
        snapshot: StateSnapshot,
        input: object | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> Result:
        state = await self.state_store.load(snapshot.state_ref)
        state.status = TaskStatus.WORKING
        if input is not None:
            state.working_memory["resume_input"] = input
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
            state.history.append(
                Turn(decision=answer_decision, observation=answer_obs),
            )
            state.step += 1
        return await self._loop(state, max_steps)

    async def _loop(self, state: AgentState, max_steps: int) -> Result:
        """六步闭集编排（ADR-0066）。

        state mutation 经 ``self.reducer``；hook 触发直接调
        ``self.hooks.trigger(hook_name, state, **kwargs)``。
        """
        decision = observation = reflection = None
        for step in range(state.step, max_steps):
            state = self.reducer.apply_step_advanced(state, step)
            try:
                # ── Phase 1: Perceive (PR3a — Hub is the SOLE emitter) ──
                await self.hooks.trigger(HookEvent.PRE_PERCEIVE.value, state)
                manifest = await self.perceive_hub.perceive(state)
                state = self.reducer.apply_perception(state, manifest)
                await self.hooks.trigger(HookEvent.POST_PERCEIVE.value, state)
                # ── Phase 2: Think ──
                await self.hooks.trigger(HookEvent.PRE_THINK.value, state)
                decision = await self.brain.think(state)
                await self.hooks.trigger(HookEvent.POST_THINK.value, state, decision=decision)
                # ── Phase 3: Act ──
                await self.hooks.trigger(HookEvent.PRE_ACT.value, state, decision=decision)
                observation = await self.body.act(decision, state)
                await self.hooks.trigger(
                    HookEvent.POST_ACT.value, state, decision=decision, observation=observation
                )
                # ── Phase 3.5: Sync activation state (PR5) ──
                state = self.reducer.apply_activation(state, _drain_newly_activated(state))
                # ── Phase 4: Reflect ──
                await self.hooks.trigger(
                    HookEvent.PRE_REFLECT.value, state, observation=observation
                )
                reflection = await self.brain.reflect(state, observation)
                await self.hooks.trigger(HookEvent.POST_REFLECT.value, state, reflection=reflection)
                # ── Phase 5: Record + Remember ──
                turn = Turn(decision=decision, observation=observation, reflection=reflection)
                state = self.reducer.apply_turn(state, turn)
                await self.memory.update(state, observation, reflection)
                state = self.reducer.apply_memory(state, None)
            except ApprovalPendingError as exc:
                snap = await self._checkpoint(state, reason=SnapshotReason.PRE_APPROVAL)
                state = self.reducer.apply_paused(state, snap.state_ref)
                await self.hooks.trigger(HookEvent.ON_PAUSE.value, state)
                result = Result.from_state(state)
                result.extra["state_snapshot"] = snap
                result.extra["approval_request"] = exc.approval_request
                return result
            except Exception as err:
                _log.exception("unexpected_loop_error", step=step, error=str(err))
                await self.hooks.trigger(HookEvent.ON_ERROR.value, state, error=err)
                state = self.reducer.apply_error(state, err)
                await self._checkpoint(state, reason=SnapshotReason.ON_ERROR)
                break
            # ── Phase 6: Checkpoint + Stop ──
            await self._checkpoint(state)
            stop = self.stop_rule.decide(state, decision, observation, reflection)
            state = self.reducer.apply_stop(state, stop)
            if stop.should_stop:
                if stop.reason == StopReason.BUDGET_EXCEEDED:
                    await self.hooks.trigger(
                        HookEvent.ON_ERROR.value, state, error=BudgetExceededError()
                    )
                break
        await self.hooks.trigger(HookEvent.ON_COMPLETE.value, state)
        self._apply_artifact_closure(state)
        return Result.from_state(state)

    @staticmethod
    def _apply_artifact_closure(state: AgentState) -> None:
        """Append workspace deliverables to final output (LobeHub workRegistration-style).

        仍原地修改 state.final_output / state.status；计划在 AgentState
        转 frozen 后迁入 reducer.apply_artifact_closure。
        """
        closure = synthesize_artifact_closure()
        if closure:
            if state.final_output:
                if closure.strip() not in state.final_output:
                    state.final_output = state.final_output.rstrip() + "\n\n" + closure
            else:
                state.final_output = closure
            if state.status == TaskStatus.WORKING:
                state.status = TaskStatus.COMPLETED

    async def _checkpoint(
        self, state: AgentState, reason: SnapshotReason = SnapshotReason.PERIODIC
    ) -> StateSnapshot:
        snap = state.snapshot(reason=reason)
        ref = await self.state_store.save(state)
        snap.state_ref = ref
        return snap


def _drain_newly_activated(state: AgentState) -> tuple:
    """Drain the contextvar activation scope into a tuple."""
    from lca.contracts.models.core.activation import ActivatedSkill

    return tuple(
        ActivatedSkill(
            skill_id=s.skill_id,
            name=s.name,
            activated_at_step=state.step,
        )
        for s in get_newly_activated(state.activated_skills)
    )


__all__ = ["CognitiveRuntime"]
