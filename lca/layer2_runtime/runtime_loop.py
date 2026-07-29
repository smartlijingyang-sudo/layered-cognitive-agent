"""CognitiveRuntime —— 核心认知循环（~25行 Loop，ADR-0002）。

Loop 本体只负责六步骨架串联 + 循环控制，
所有业务判定（降级、输出提取、终止条件）通过 StepOutcomePolicy 注入，
所有可观测事件通过 Hook 发布，Loop 不直接持有 EventBus。
"""

from __future__ import annotations

import uuid
from typing import Any

from lca.contracts.budget import create_budget
from lca.contracts.decision import Observation, Reflection, StructuredDecision
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols import (
    Body,
    BrainStrategy,
    MemorySystem,
    RosterAware,
    Runtime,
    SharedStoreBindable,
    StateStore,
    StepOutcomePolicy,
    TransportBindable,
)


class CognitiveRuntime(Runtime):
    ...

    def configure(self, **capabilities: Any) -> None:
        if "transport" in capabilities and isinstance(self.body, TransportBindable):
            self.body.bind_transport(capabilities["transport"])
        if "team_roster" in capabilities and isinstance(self.brain, RosterAware):
            self.brain.set_team_roster(capabilities["team_roster"])
        if "shared_memory" in capabilities and isinstance(self.memory, SharedStoreBindable):
            self.memory.bind_shared_store(capabilities["shared_memory"])
        if "team_progress" in capabilities:
            self._team_progress = capabilities["team_progress"]


from lca.contracts.result import (
    ApprovalPendingError,
    BudgetExceededError,
    Result,
)
from lca.contracts.state import StateSnapshot, TypedState
from lca.contracts.types import StepOutcome, Turn


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


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
        state_store: StateStore,
        outcome_policy: StepOutcomePolicy | None = None,
    ):
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.state_store = state_store
        self.outcome_policy = outcome_policy or _DefaultOutcomePolicy()
        self._team_progress: Any = None

    def configure(self, **capabilities: Any) -> None:
        if "transport" in capabilities and hasattr(self.body, "bind_transport"):
            self.body.bind_transport(capabilities["transport"])
        if "team_roster" in capabilities and hasattr(self.brain, "set_team_roster"):
            self.brain.set_team_roster(capabilities["team_roster"])
        if "shared_memory" in capabilities and hasattr(self.memory, "bind_shared_store"):
            self.memory.bind_shared_store(capabilities["shared_memory"])
        if "team_progress" in capabilities:
            self._team_progress = capabilities["team_progress"]

    async def run(
        self,
        task: str,
        max_steps: int = 10,
        max_wall_clock_seconds: int | None = None,
        **context: str,
    ) -> Result:
        state = TypedState(
            trace_id=_new_id("trace"),
            task=task,
            budget=create_budget(
                max_steps=max_steps,
                max_wall_clock_seconds=max_wall_clock_seconds,
            ),
            agent_role=context.get("agent_role", ""),
            delegated_by=context.get("delegated_by", ""),
            team_progress=self._team_progress,
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
        observation: Observation | None = None
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
                await self.hooks.trigger(
                    "post_act", state, decision=decision, observation=observation
                )

                await self.hooks.trigger("pre_reflect", state, observation=observation)
                reflection = await self.brain.reflect(state, observation)
                await self.hooks.trigger("post_reflect", state, reflection=reflection)

                # 两阶段历史：先记 decision+observation，reflect 后补齐 reflection
                state.history.append(
                    Turn(decision=decision, observation=observation, reflection=reflection)
                )
                await self.memory.update_multi_level(state, observation, reflection)

            except ApprovalPendingError:
                self._checkpoint(state, reason="pre_approval")
                state.status = "waiting_human"
                await self.hooks.trigger("on_pause", state)
                return self._summarize(state)

            except Exception as err:
                await self.hooks.trigger("on_error", state, error=err)
                state.status = "failed"
                self._checkpoint(state, reason="on_error")
                state.extra["error"] = str(err)
                break

            self._checkpoint(state)
            outcome = self.outcome_policy.resolve(state, decision, observation, reflection)
            if outcome.final_output is not None:
                state.working_memory["final_output"] = outcome.final_output

            if state.budget.exceeded():
                await self.hooks.trigger("on_error", state, error=BudgetExceededError())
                budget_outcome = self.outcome_policy.resolve_budget_exceeded(observation, state)
                if budget_outcome.final_output is not None:
                    state.working_memory["final_output"] = budget_outcome.final_output
                state.status = budget_outcome.status or state.status  # type: ignore[assignment]
                break

            if outcome.should_stop:
                state.status = outcome.status or "completed"  # type: ignore[assignment]
                break

        await self.hooks.trigger("on_complete", state)
        return self._summarize(state)

    def _checkpoint(self, state: TypedState, reason: str = "periodic") -> None:
        state.checkpoints.append(state.snapshot(reason=reason))

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


class _DefaultOutcomePolicy(StepOutcomePolicy):
    """最小内置 OutcomePolicy——无终止条件，仅用于 Loop 在无外部注入时的兜底。

    实际部署时应使用 layer2_runtime.outcome_policies.DefaultStepOutcomePolicy，
    它包含 respond/handoff/降级 等完整业务判定。
    """

    def resolve(
        self,
        state: TypedState,
        decision: StructuredDecision | None,
        observation: Observation | None,
        reflection: Reflection | None,
    ) -> StepOutcome:
        return StepOutcome()

    def resolve_budget_exceeded(
        self,
        observation: Observation | None,
        state: TypedState,
    ) -> StepOutcome:
        last_ok = observation is not None and getattr(observation, "success", False)
        return StepOutcome(should_stop=True, status="completed" if last_ok else "failed")
