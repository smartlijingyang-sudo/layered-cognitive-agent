"""CognitiveRuntime —— 核心认知循环（ADR-0002）。
Loop 只做编排：perceive → think → act → reflect → record → checkpoint → judge。
终止判定完全委托给 StopRule，业务逻辑零泄漏。
L2 层职责：
    将 Brain（认知）、Body（执行）、Memory（记忆）三大能力
    串联为可中断、可恢复、可观测的闭环。所有横切关注点
    （hook、checkpoint、error handling）在此层统一处理。
"""

from __future__ import annotations

import structlog

from lca.contracts.budget import DEFAULT_MAX_STEPS, create_budget
from lca.contracts.enums import RoleMode, SnapshotReason
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols import (
    Body,
    Brain,
    MemorySystem,
    Runtime,
    StateStore,
)
from lca.contracts.result import ApprovalPendingError, BudgetExceededError, Result
from lca.contracts.run_context import RunContext
from lca.contracts.state import AgentState, StateSnapshot
from lca.contracts.stop import StopReason, StopRule
from lca.contracts.types import Turn

_log = structlog.get_logger("lca.runtime_loop")


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
        judge: StopRule,
    ) -> None:
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.state_store = state_store
        self.judge = judge

    async def run(
        self,
        task: str,
        ctx: RunContext | None = None,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        agent_role: str = "",
    ) -> Result:
        state = AgentState(
            trace_id=(ctx.trace_id if ctx and ctx.trace_id else new_id("trace")),
            task=task,
            budget=create_budget(
                max_steps=max_steps, max_wall_clock_seconds=max_wall_clock_seconds
            ),
            agent_role=agent_role,
            from_role=(ctx.from_role if ctx else ""),
            member_status=(ctx.member_status if ctx else None),
            role_mode=(ctx.role_mode if ctx else RoleMode.SOLO),
            teammates=list(ctx.teammates) if ctx else [],
            delegate_max_attempts=(ctx.delegate_max_attempts if ctx else 3),
        )
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
            7. judge    — 委托 StopRule 决定是否终止
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
                # ── Phase 4: Reflect ──
                await self.hooks.trigger("pre_reflect", state, observation=observation)
                reflection = await self.brain.reflect(state, observation)
                await self.hooks.trigger("post_reflect", state, reflection=reflection)
                # ── Phase 5: Record ──
                state.history.append(
                    Turn(decision=decision, observation=observation, reflection=reflection)
                )
                await self.memory.update(state, observation, reflection)
            except ApprovalPendingError:
                # 人工审批中断：保存快照后暂停循环
                await self._checkpoint(state, reason=SnapshotReason.PRE_APPROVAL)
                state.status = TaskStatus.INPUT_REQUIRED
                await self.hooks.trigger("on_pause", state)
                return Result.from_state(state)
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
            # ── Phase 7: Judge ──
            signal = self.judge.decide(state, decision, observation, reflection)
            if signal.should_stop:
                if signal.reason == StopReason.BUDGET_EXCEEDED:
                    await self.hooks.trigger("on_error", state, error=BudgetExceededError())
                if signal.status is not None:
                    state.status = signal.status
                break
        await self.hooks.trigger("on_complete", state)
        return Result.from_state(state)

    async def _checkpoint(
        self, state: AgentState, reason: SnapshotReason = SnapshotReason.PERIODIC
    ) -> StateSnapshot:
        snap = state.snapshot(reason=reason)
        ref = await self.state_store.save(state)
        snap.state_ref = ref
        return snap
