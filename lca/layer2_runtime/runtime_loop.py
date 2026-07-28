"""CognitiveRuntime —— 核心认知循环（~25行 Loop，第6节参考实现的可运行版本）。"""

from __future__ import annotations

import uuid
from typing import Any

from lca.contracts.decision import Reflection, StructuredDecision
from lca.contracts.protocols import (
    Body,
    BrainStrategy,
    EventBus,
    HookRegistry,
    MemorySystem,
    Runtime,
    StateStore,
)
from lca.contracts.result import ApprovalPendingError, BudgetExceededError, Result
from lca.contracts.state import Budget, StateSnapshot, TypedState


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class CognitiveRuntime(Runtime):
    """
    核心 Loop: perceive -> think -> act -> observe -> reflect -> update
    所有 Prompt 模板、压缩策略、Strategy 切换、错误恢复、人工审批
    全部通过 Hook 与 Strategy 注册进来，Loop 本体保持稳定不变。
    """

    def __init__(
        self,
        brain: BrainStrategy,
        body: Body,
        memory: MemorySystem,
        hooks: HookRegistry,
        event_bus: EventBus,
        state_store: StateStore,
    ):
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.event_bus = event_bus
        self.state_store = state_store

    def configure(self, **capabilities: Any) -> None:
        if "transport" in capabilities and hasattr(self.body, "bind_transport"):
            self.body.bind_transport(capabilities["transport"])
        if "team_roster" in capabilities and hasattr(self.brain, "set_team_roster"):
            self.brain.set_team_roster(capabilities["team_roster"])
        if "shared_memory" in capabilities and hasattr(self.memory, "bind_shared_store"):
            self.memory.bind_shared_store(capabilities["shared_memory"])

    def default_budget(self) -> Budget:
        return Budget(max_steps=10, max_wall_clock_seconds=30)

    async def run(self, task: str, max_steps: int = 10, **context: str) -> Result:
        state = TypedState(
            trace_id=_new_id("trace"),
            task=task,
            budget=self.default_budget(),
            agent_role=context.get("agent_role", ""),
            delegated_by=context.get("delegated_by", ""),
        )
        await self.hooks.trigger("on_start", state)
        return await self._loop(state, max_steps)

    async def resume(self, snapshot: StateSnapshot, max_steps: int = 10) -> Result:
        """从任意 Checkpoint 恢复——挂起等待人工审批/暂停的任务由此续跑。"""
        state = await self.state_store.load(snapshot.state_ref)
        state.status = "running"
        return await self._loop(state, max_steps)

    async def _loop(self, state: TypedState, max_steps: int) -> Result:
        decision: StructuredDecision | None = None
        reflection: Reflection | None = None

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
                await self.hooks.trigger("post_act", state, observation=observation)

                if decision.action_type == "respond":
                    state.working_memory["final_output"] = decision.response_text

                await self.hooks.trigger("pre_reflect", state, observation=observation)
                reflection = await self.brain.reflect(state, observation)
                await self.hooks.trigger("post_reflect", state, reflection=reflection)

                await self.memory.update_multi_level(state, observation, reflection)

            except ApprovalPendingError:
                state.status = "waiting_human"
                state.checkpoints.append(state.snapshot(reason="pre_approval"))
                await self.hooks.trigger("on_pause", state)
                return self._summarize(state)

            except Exception as err:
                await self.hooks.trigger("on_error", state, error=err)
                state.status = "failed"
                state.checkpoints.append(state.snapshot(reason="on_error"))
                state.extra["error"] = str(err)
                break

            state.checkpoints.append(state.snapshot())
            self.event_bus.emit(
                "step_completed",
                {"step": state.step, "status": state.status},
                state.trace_id,
            )

            if state.budget.exceeded():
                await self.hooks.trigger("on_error", state, error=BudgetExceededError())
                state.status = "failed"
                break

            if self._should_stop(decision, reflection):
                state.status = "completed"
                break

        await self.hooks.trigger("on_complete", state)
        return self._summarize(state)

    def _should_stop(
        self, decision: StructuredDecision | None, reflection: Reflection | None
    ) -> bool:
        if decision is None or reflection is None:
            return False
        if decision.action_type == "handoff":
            return True
        return decision.action_type == "respond" and reflection.verdict != "needs_correction"

    def _summarize(self, state: TypedState) -> Result:
        final_ref = f"mem://{state.trace_id}/{state.step}"
        status = "completed" if state.status == "running" else state.status
        return Result(
            trace_id=state.trace_id,
            status=status,
            output=state.working_memory.get("final_output"),
            final_state_ref=final_ref,
            total_steps=state.step + 1,
            budget_used=state.budget,
            error=state.extra.get("error"),
        )
