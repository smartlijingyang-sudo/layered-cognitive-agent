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

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.enums import ActionType, HookEvent, SnapshotReason
from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.budget import DEFAULT_MAX_STEPS, create_budget
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY
from lca.contracts.models.core.decision import Decision, Observation, Reflection, ToolCall, Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import ApprovalPendingError, BudgetExceededError, Result
from lca.contracts.models.core.state import AgentState, StateSnapshot
from lca.contracts.models.core.stop import StopDecision, StopReason
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
from lca.contracts.protocols.control_plan import ControlPlan
from lca.contracts.protocols.plan import CompiledRunPlan
from lca.contracts.protocols.reducer import LoopTopology
from lca.layer0_infra.observability import get_span_context
from lca.layer0_infra.skills.activation_scope import get_newly_activated
from lca.layer2_runtime.completion.artifact_closure import synthesize_artifact_closure
from lca.layer2_runtime.control_policies import (
    ControlPolicyContext,
    DefaultControlPolicyEngine,
)
from lca.layer2_runtime.control_runtime import (
    ControlEvaluation,
    ControlSelection,
    ControlVerdictKind,
    aggregate_control_verdicts,
    select_control_entries,
)
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
        control_policies: DefaultControlPolicyEngine | None = None,
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
        self.control_policies = (
            control_policies if control_policies is not None else DefaultControlPolicyEngine()
        )

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
        if self.compiled_plan is not None and self.phase_executors:
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
        return await self._loop(state, max_steps)

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
        
        # 检查是否有声明式 cursor，如果有则委托给 declarative driver
        phase_cursor = getattr(state, "phase_cursor", None)
        if phase_cursor is not None and self.compiled_plan is not None:
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
        
        # 回退到旧循环（将在 Task 6 中删除）
        return await self._loop(state, max_steps)

    def select_control(self, slot: ControlSlot, state: AgentState) -> ControlSelection | None:
        """返回当前阶段激活的控制投稿；诊断调用不改变运行时。"""
        if self.control_plan is None:
            return None
        return select_control_entries(self.control_plan, slot, state)

    def evaluate_control(
        self,
        slot: ControlSlot,
        state: AgentState,
        *,
        decision: Decision | None = None,
        observation: Observation | None = None,
        reflection: Reflection | None = None,
        checkpoint_reason: SnapshotReason | None = None,
    ) -> ControlEvaluation | None:
        """执行活跃投稿并以唯一聚合器生成该槽位的有效 verdict。"""
        if self.control_plan is None:
            return None
        selection = select_control_entries(self.control_plan, slot, state)
        verdicts = self.control_policies.evaluate(
            selection,
            ControlPolicyContext(
                state=state,
                decision=decision,
                observation=observation,
                reflection=reflection,
                checkpoint_reason=checkpoint_reason,
            ),
        )
        return aggregate_control_verdicts(selection, verdicts)

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
                perceive_control = self.evaluate_control(ControlSlot.PERCEIVE_CONTEXT, state)
                if _must_stop(perceive_control):
                    return await self._finish_control_stop(state, perceive_control)
                await self.hooks.trigger(HookEvent.PRE_PERCEIVE.value, state)
                manifest = await self.perceive_hub.perceive(state)
                state = self.reducer.apply_perception(state, manifest)
                await self.hooks.trigger(HookEvent.POST_PERCEIVE.value, state)
                # ── Phase 2: Think ──
                self.evaluate_control(ControlSlot.THINK_GUARD, state)
                await self.hooks.trigger(HookEvent.PRE_THINK.value, state)
                decision = await self.brain.think(state)
                think_control = self.evaluate_control(
                    ControlSlot.THINK_GUARD, state, decision=decision
                )
                if _must_stop(think_control):
                    return await self._finish_control_stop(state, think_control)
                await self.hooks.trigger(HookEvent.POST_THINK.value, state, decision=decision)
                # ── Phase 3: Act ──
                act_evaluations = tuple(
                    self.evaluate_control(slot, state, decision=decision)
                    for slot in (
                        ControlSlot.ACT_AUTHORIZE,
                        ControlSlot.ACT_BUDGET,
                        ControlSlot.ACT_CONSTRAIN,
                        ControlSlot.ACT_EXECUTE,
                        ControlSlot.ACT_SAFE_BOUNDARY,
                    )
                )
                await self.hooks.trigger(HookEvent.PRE_ACT.value, state, decision=decision)
                terminal_act = next(
                    (evaluation for evaluation in act_evaluations if _must_stop(evaluation)), None
                )
                if terminal_act is not None:
                    return await self._finish_control_stop(state, terminal_act)
                blocking_act = next(
                    (evaluation for evaluation in act_evaluations if _is_blocking(evaluation)), None
                )
                observation = (
                    _control_denied_observation(decision, blocking_act)
                    if blocking_act is not None
                    else await self.body.act(decision, state)
                )
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
                remember_control = self.evaluate_control(
                    ControlSlot.REMEMBER_ADMIT,
                    state,
                    decision=decision,
                    observation=observation,
                    reflection=reflection,
                )
                if not _is_blocking(remember_control):
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
            stop_control = self.evaluate_control(
                ControlSlot.STOP_DECIDE,
                state,
                decision=decision,
                observation=observation,
                reflection=reflection,
            )
            stop = (
                _control_stop_decision(stop_control)
                if _must_stop(stop_control)
                else self.stop_rule.decide(state, decision, observation, reflection)
            )
            state = self.reducer.apply_stop(state, stop)
            if stop.should_stop:
                if stop.reason == StopReason.BUDGET_EXCEEDED:
                    await self.hooks.trigger(
                        HookEvent.ON_ERROR.value, state, error=BudgetExceededError()
                    )
                break
        await self.hooks.trigger(HookEvent.ON_COMPLETE.value, state)
        state = self.reducer.apply_artifact_closure(state, synthesize_artifact_closure() or "")
        return Result.from_state(state)

    async def _checkpoint(
        self, state: AgentState, reason: SnapshotReason = SnapshotReason.PERIODIC
    ) -> StateSnapshot:
        self.evaluate_control(
            ControlSlot.OBSERVE_CHECKPOINT,
            state,
            checkpoint_reason=reason,
        )
        self.evaluate_control(
            ControlSlot.OBSERVE_WILDCARD,
            state,
            checkpoint_reason=reason,
        )
        checkpoint_count = len(state.checkpoints)
        snap = state.snapshot(reason=reason)
        try:
            ref = await self.state_store.save(state)
        except BaseException:
            if len(state.checkpoints) == checkpoint_count + 1 and state.checkpoints[-1] is snap:
                state.checkpoints.pop()
            raise
        snap.state_ref = ref
        return snap

    async def _finish_control_stop(
        self,
        state: AgentState,
        evaluation: ControlEvaluation | None,
    ) -> Result:
        """Fold a terminal control verdict through Reducer and return a final result."""
        state = self.reducer.apply_stop(state, _control_stop_decision(evaluation))
        await self._checkpoint(state, reason=SnapshotReason.ON_ERROR)
        await self.hooks.trigger(HookEvent.ON_COMPLETE.value, state)
        state = self.reducer.apply_artifact_closure(state, synthesize_artifact_closure() or "")
        return Result.from_state(state)


def _is_blocking(evaluation: ControlEvaluation | None) -> bool:
    return evaluation is not None and evaluation.is_blocking


def _must_stop(evaluation: ControlEvaluation | None) -> bool:
    return (
        evaluation is not None
        and evaluation.blocking_verdict is not None
        and evaluation.blocking_verdict.kind is ControlVerdictKind.STOP
    )


def _control_stop_decision(evaluation: ControlEvaluation | None) -> StopDecision:
    effective = evaluation.blocking_verdict if evaluation is not None else None
    detail = effective.detail if effective is not None else "control stopped run"
    reason = (
        StopReason.BUDGET_EXCEEDED
        if effective is not None and effective.kind is ControlVerdictKind.EXHAUSTED
        else StopReason.ERROR
    )
    return StopDecision(
        should_stop=True,
        reason=reason,
        final_output=detail,
        status=TaskStatus.FAILED,
    )


def _control_denied_observation(
    decision: Decision,
    evaluation: ControlEvaluation,
) -> Observation:
    effective = evaluation.blocking_verdict
    if effective is None:
        raise ValueError("blocking control evaluation has no blocking verdict")
    return Observation(
        observation_id=new_id("obs"),
        success=False,
        payload=None,
        error=f"control {evaluation.selection.slot.value} {effective.kind.value}: {effective.detail}",
        extra={
            "control_slot": evaluation.selection.slot.value,
            "control_plugin": effective.plugin_id,
            "control_verdict": effective.kind.value,
            "decision_id": decision.decision_id,
        },
    )


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
