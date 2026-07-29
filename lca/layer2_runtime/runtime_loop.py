"""CognitiveRuntime —— 核心认知循环（ADR-0002）。
Loop 只做编排：perceive → think → act → reflect → record → checkpoint → judge。
终止判定完全委托给 LoopJudge，业务逻辑零泄漏。
L2 层职责：
    将 Brain（认知）、Body（执行）、Memory（记忆）三大能力
    串联为可中断、可恢复、可观测的闭环。所有横切关注点
    （hook、checkpoint、error handling）在此层统一处理。
"""

from __future__ import annotations

import logging

from lca.contracts.budget import DEFAULT_MAX_STEPS, create_budget
from lca.contracts.enums import SnapshotReason
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.loop_judge import LoopJudge, TerminationReason
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols import (
    Body,
    BrainStrategy,
    CompletionPolicy,
    MemorySystem,
    Runtime,
    StateStore,
    SupportsCompletionGuard,
)
from lca.contracts.result import ApprovalPendingError, BudgetExceededError, Result
from lca.contracts.state import StateSnapshot, TypedState
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.contracts.types import Turn

_logger = logging.getLogger(__name__)


class CognitiveRuntime(Runtime):
    """核心认知循环实现（ADR-0002）。
    将 Brain（认知）、Body（执行）、Memory（记忆）串联为
    perceive → think → act → reflect 闭环。
    终止判定完全委托给 LoopJudge，本类不含业务逻辑。
    """

    def __init__(
        self,
        brain: BrainStrategy,
        body: Body,
        memory: MemorySystem,
        hooks: HookRegistry,
        state_store: StateStore,
        judge: LoopJudge,
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
        max_steps: int = DEFAULT_MAX_STEPS,
        max_wall_clock_seconds: int | None = None,
        team_progress: DelegationLedgerProtocol | None = None,
        **context: str,
    ) -> Result:
        state = TypedState(
            trace_id=new_id("trace"),
            task=task,
            budget=create_budget(
                max_steps=max_steps, max_wall_clock_seconds=max_wall_clock_seconds
            ),
            agent_role=context.get("agent_role", ""),
            delegated_by=context.get("delegated_by", ""),
            team_progress=team_progress,
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

    async def _loop(self, state: TypedState, max_steps: int) -> Result:
        """执行 perceive → think → act → reflect 认知主循环。
        循环流程：
            1. perceive — 感知环境、检索记忆
            2. think    — 结构化决策
            3. act      — 执行动作（工具调用 / 回复 / 委派）
            4. reflect  — 反思结果、判定质量
            5. record   — 追加 Turn 到历史、更新多层记忆
            6. checkpoint — 持久化状态快照
            7. judge    — 委托 LoopJudge 决定是否终止
        """
        decision = observation = reflection = None
        for step in range(state.step, max_steps):
            state.step = step
            state.budget.used_steps = step
            try:
                # ── Phase 1: Perceive ──
                await self.hooks.trigger("pre_perceive", state)
                state = await self.memory.perceive(state)
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
                return self._summarize(state)
            except Exception as err:
                # 信任边界处的兜底捕获（L2 是 Agent 最外层循环）：
                # 任何未预料的异常都不能向上传播导致进程崩溃，
                # 而是标记 FAILED、持久化快照、通知 hook 后安全退出。
                _logger.exception(
                    "CognitiveRuntime._loop: unexpected error at step %d",
                    step,
                    exc_info=err,
                )
                await self.hooks.trigger("on_error", state, error=err)
                state.status = TaskStatus.FAILED
                await self._checkpoint(state, reason=SnapshotReason.ON_ERROR)
                state.last_error = str(err)
                break
            # ── Phase 6: Checkpoint ──
            await self._checkpoint(state)
            # ── Phase 7: Judge ──
            signal = self.judge.judge(state, decision, observation, reflection)
            if signal.should_stop:
                if signal.reason == TerminationReason.BUDGET_EXCEEDED:
                    await self.hooks.trigger("on_error", state, error=BudgetExceededError())
                if signal.status is not None:
                    state.status = signal.status
                break
        await self.hooks.trigger("on_complete", state)
        return self._summarize(state)

    async def _checkpoint(
        self, state: TypedState, reason: SnapshotReason = SnapshotReason.PERIODIC
    ) -> StateSnapshot:
        snap = state.snapshot(reason=reason)
        ref = await self.state_store.save(state)
        snap.state_ref = ref
        return snap

    def _summarize(self, state: TypedState) -> Result:
        final_ref = f"mem://{state.trace_id}/{state.step}"
        status = TaskStatus.COMPLETED if state.status == TaskStatus.WORKING else state.status
        return Result(
            trace_id=state.trace_id,
            status=status,
            output=state.final_output
            if isinstance(state.final_output, str) or state.final_output is None
            else str(state.final_output),
            final_state_ref=final_ref,
            total_steps=state.step + 1,
            budget_used=state.budget,
            error=state.last_error,
        )

    def install_completion_guard(self, policy: CompletionPolicy) -> None:
        """委托 Brain 自管内部评估管线，安装确定性收尾 guardrail。
        通过结构化 isinstance 探测能力，而非 hasattr 字符串猜测：
        不支持时必须显式报错，避免调用方以为 guardrail 已生效、
        实际却被静默跳过。
        """
        if not isinstance(self.brain, SupportsCompletionGuard):
            raise TypeError(
                f"{type(self.brain).__name__} 未实现 SupportsCompletionGuard，"
                "无法安装 completion guard"
            )
        self.brain.install_completion_guard(policy)
