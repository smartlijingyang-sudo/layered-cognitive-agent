"""CognitiveRuntime —— 核心认知循环（ADR-0002）。
Loop 只做编排：perceive → think → act → reflect → record → checkpoint → stop。
终止判定完全委托给 StopRule，业务逻辑零泄漏。
L2 层职责：
    将 Brain（认知）、Body（执行）、Memory（记忆）三大能力
    串联为可中断、可恢复、可观测的闭环。所有横切关注点
    （hook、checkpoint、error handling）在此层统一处理。
"""

from __future__ import annotations

import structlog

from lca.contracts.atoms.enums import ActionType, SnapshotReason
from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.activation import ActivatedSkill
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
    Runtime,
    StateStore,
    StopRule,
)
from lca.layer0_infra.observability import get_span_context
from lca.layer0_infra.skills.activation_scope import get_newly_activated
from lca.layer2_runtime.completion.artifact_closure import synthesize_artifact_closure

_log = structlog.get_logger("lca.runtime_loop")

_LOOP_WARNING_WM_KEY = "loop_warning"
_LOOP_CONSECUTIVE_THRESHOLD = 3


class CognitiveRuntime(Runtime):
    """核心认知循环实现（ADR-0002）。
    将 Brain（认知）、Body（执行）、Memory（记忆）串联为
    perceive → think → act → reflect 闭环。
    终止判定完全委托给 StopRule，本类不含业务逻辑。
    """

    def __init__(
        self,
        brain: Brain,
        body: Body,
        memory: MemorySystem,
        hooks: HookRegistry,
        state_store: StateStore,
        stop_rule: StopRule,
    ) -> None:
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.state_store = state_store
        self.stop_rule = stop_rule

    async def run(
        self,
        task: str,
        ctx: RunContext | None = None,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        agent_role: str = "",
    ) -> Result:
        # Prefer explicit RunContext.trace_id, then active span context (team chain), else new.
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
            state.working_memory[PRIOR_CONVERSATION_WM_KEY] = ctx.extra[PRIOR_CONVERSATION_WM_KEY]
        await self.hooks.trigger("on_start", state)
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
        """执行 perceive → think → act → reflect 认知主循环。
        循环流程：
            1. perceive — 感知环境、检索记忆
            2. think    — 结构化决策
            3. act      — 执行动作（工具调用 / 回复 / 委派）
            4. reflect  — 反思结果、判定质量
            5. record   — 追加 Turn 到历史、更新多层记忆
            6. checkpoint — 持久化状态快照
            7. stop     — 委托 StopRule 决定是否终止
        """
        decision = observation = reflection = None
        for step in range(state.step, max_steps):
            state.step = step
            state.budget.used_steps = step
            try:
                # ── Phase 1: Perceive ──
                await self.hooks.trigger("pre_perceive", state)
                state = await self.memory.perceive(state)
                await self.hooks.trigger("post_perceive", state)
                # ── Phase 2: Think ──
                await self.hooks.trigger("pre_think", state)
                decision = await self.brain.think(state)
                await self.hooks.trigger("post_think", state, decision=decision)
                # ── Phase 3: Act ──
                await self.hooks.trigger("pre_act", state, decision=decision)
                observation = await self.body.act(decision, state)
                await self.hooks.trigger(
                    "post_act", state, decision=decision, observation=observation
                )
                # ── Phase 3.5: Sync activation state ──
                self._sync_activated_skills(state)
                # ── Phase 3.6: Loop intervention ──
                self._detect_and_inject_loop_warning(state, decision, observation)
                # ── Phase 4: Reflect ──
                await self.hooks.trigger("pre_reflect", state, observation=observation)
                reflection = await self.brain.reflect(state, observation)
                await self.hooks.trigger("post_reflect", state, reflection=reflection)
                # ── Phase 5: Record ──
                state.history.append(
                    Turn(decision=decision, observation=observation, reflection=reflection)
                )
                await self.memory.update(state, observation, reflection)
            except ApprovalPendingError as exc:
                # 人工审批中断：保存快照后暂停循环
                snap = await self._checkpoint(state, reason=SnapshotReason.PRE_APPROVAL)
                state.status = TaskStatus.INPUT_REQUIRED
                await self.hooks.trigger("on_pause", state)
                result = Result.from_state(state)
                result.extra["state_snapshot"] = snap
                result.extra["approval_request"] = exc.approval_request
                return result
            except Exception as err:
                # 信任边界处的兜底捕获（L2 是 Agent 最外层循环）：
                # 任何未预料的异常都不能向上传播导致进程崩溃，
                # 而是标记 FAILED、持久化快照、通知 hook 后安全退出。
                _log.exception("unexpected_loop_error", step=step, error=str(err))
                await self.hooks.trigger("on_error", state, error=err)
                state.status = TaskStatus.FAILED
                await self._checkpoint(state, reason=SnapshotReason.ON_ERROR)
                state.last_error = str(err)
                break
            # ── Phase 6: Checkpoint ──
            await self._checkpoint(state)
            # ── Phase 7: Stop ──
            stop = self.stop_rule.decide(state, decision, observation, reflection)
            if stop.should_stop:
                if stop.reason == StopReason.BUDGET_EXCEEDED:
                    await self.hooks.trigger("on_error", state, error=BudgetExceededError())
                if stop.status is not None:
                    state.status = stop.status
                break
        await self.hooks.trigger("on_complete", state)
        self._apply_artifact_closure(state)
        return Result.from_state(state)

    @staticmethod
    def _apply_artifact_closure(state: AgentState) -> None:
        """Append workspace deliverables to final output (LobeHub workRegistration-style)."""
        closure = synthesize_artifact_closure()
        if not closure:
            return
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

    @staticmethod
    def _sync_activated_skills(state: AgentState) -> None:
        """Sync contextvar activation_scope → AgentState (one-way)."""
        newly = get_newly_activated(state.activated_skills)
        for skill in newly:
            state.activated_skills.append(
                ActivatedSkill(
                    skill_id=skill.skill_id,
                    name=skill.name,
                    activated_at_step=state.step,
                )
            )

    # ── Loop intervention (Phase 3.6) ──────────────────────────────

    @staticmethod
    def _detect_and_inject_loop_warning(
        state: AgentState,
        decision: Decision | None,
        observation: Observation | None,
    ) -> None:
        """Inline loop detection — injects warning into working_memory for next think phase."""
        if decision is None or decision.action_type != ActionType.USE_TOOL:
            return
        tool_calls = decision.tool_calls or []
        if not tool_calls:
            return
        current_tool = tool_calls[0].tool_name

        # Count consecutive calls to the same tool in history
        consecutive = 0
        for turn in reversed(state.history):
            if (
                turn.decision.action_type == ActionType.USE_TOOL
                and turn.decision.tool_calls
                and turn.decision.tool_calls[0].tool_name == current_tool
            ):
                consecutive += 1
            else:
                break

        if consecutive >= _LOOP_CONSECUTIVE_THRESHOLD:
            tool_failed = observation is not None and not observation.success
            msg = (
                f"⚠️ 你已连续 {consecutive} 次调用工具 {current_tool}"
                f"{'，且最近调用失败' if tool_failed else ''}。"
                f"请换一种方法或工具，不要继续重复相同的调用。"
            )
            state.working_memory[_LOOP_WARNING_WM_KEY] = msg
            _log.info(
                "loop_intervention",
                tool=current_tool,
                consecutive=consecutive,
                failed=tool_failed,
            )
