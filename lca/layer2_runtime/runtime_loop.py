"""CognitiveRuntime —— 核心认知循环（ADR-0002）。

Loop 只做编排：perceive → think → act → reflect → record → checkpoint → judge。
终止判定完全委托给 LoopJudge，业务逻辑零泄漏。
"""

from __future__ import annotations

from collections.abc import Callable

from lca.contracts.budget import create_budget
from lca.contracts.enums import SnapshotReason
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.loop_judge import LoopJudge, TerminationReason
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols import (
    Body,
    BrainStrategy,
    CandidateEvaluationPipeline,
    MemorySystem,
    Runtime,
    StateStore,
)
from lca.contracts.result import ApprovalPendingError, BudgetExceededError, Result
from lca.contracts.state import StateSnapshot, TypedState
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.contracts.types import Turn


class CognitiveRuntime(Runtime):
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
        max_steps: int = 10,
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
        self, snapshot: StateSnapshot, input: object | None = None, max_steps: int = 10
    ) -> Result:
        state = await self.state_store.load(snapshot.state_ref)
        state.status = TaskStatus.WORKING
        if input is not None:
            state.working_memory["resume_input"] = input
        return await self._loop(state, max_steps)

    async def _loop(self, state: TypedState, max_steps: int) -> Result:
        decision = observation = reflection = None
        for step in range(state.step, max_steps):
            state.step = step
            state.budget.used_steps = step
            try:
                await self.hooks.trigger("pre_perceive", state)
                state = await self.memory.perceive_and_retrieve(state)

                await self.hooks.trigger("pre_think", state)
                decision = await self.brain.think(state)
                await self.hooks.trigger("post_think", state, decision=decision)

                await self.hooks.trigger("pre_act", state, decision=decision)
                observation = await self.body.act(decision, state)
                await self.hooks.trigger(
                    "post_act", state, decision=decision, observation=observation
                )

                await self.hooks.trigger("pre_reflect", state, observation=observation)
                reflection = await self.brain.reflect(state, observation)
                await self.hooks.trigger("post_reflect", state, reflection=reflection)

                state.history.append(
                    Turn(decision=decision, observation=observation, reflection=reflection)
                )
                await self.memory.update_multi_level(state, observation, reflection)
            except ApprovalPendingError:
                await self._checkpoint(state, reason=SnapshotReason.PRE_APPROVAL)
                state.status = TaskStatus.INPUT_REQUIRED
                await self.hooks.trigger("on_pause", state)
                return self._summarize(state)
            except Exception as err:
                await self.hooks.trigger("on_error", state, error=err)
                state.status = TaskStatus.FAILED
                await self._checkpoint(state, reason=SnapshotReason.ON_ERROR)
                state.last_error = str(err)
                break

            await self._checkpoint(state)

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

    def wrap_evaluation_pipeline(
        self,
        wrapper: Callable[[CandidateEvaluationPipeline], CandidateEvaluationPipeline],
    ) -> None:
        """委托 Brain 自管内部评估管线的装饰。"""
        if hasattr(self.brain, "wrap_evaluation_pipeline"):
            self.brain.wrap_evaluation_pipeline(wrapper)
