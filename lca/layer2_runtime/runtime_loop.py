"""CognitiveRuntime —— 核心认知循环（~25行 Loop，第6节参考实现的可运行版本）。"""

from __future__ import annotations

import uuid
from typing import Any

from lca.contracts.budget import create_budget
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
from lca.contracts.result import (
    ApprovalPendingError,
    BudgetExceededError,
    Result,
    ToolExecutionError,
)
from lca.contracts.state import StateSnapshot, TypedState
from lca.layer2_runtime.fallback_handler import FALLBACK_DEGRADATION_KEY, FallbackActionHandler


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
        fallback_handler: FallbackActionHandler | None = None,
    ):
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.event_bus = event_bus
        self.state_store = state_store
        self.fallback_handler = fallback_handler or FallbackActionHandler()
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
                observation = await self._act_with_fallback(decision, state)
                await self.hooks.trigger(
                    "post_act", state, decision=decision, observation=observation
                )

                # 降级为 respond 等价时，保存最终输出 + 发出可观测事件
                if FALLBACK_DEGRADATION_KEY in observation.extra and observation.success:
                    original = observation.extra[FALLBACK_DEGRADATION_KEY]
                    if decision and decision.response_text:
                        state.working_memory["final_output"] = decision.response_text
                    self.event_bus.emit(
                        "action_degraded",
                        {
                            "original_action_type": original,
                            "degraded_to": "respond",
                            "step": state.step,
                        },
                        state.trace_id,
                    )

                if decision and decision.action_type == "respond":
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
                # 预算耗尽时，若最后一步成功，视为自然终止（agent 已产出有效工作）
                last_ok = observation is not None and getattr(observation, "success", False)
                state.status = "completed" if last_ok else "failed"
                # 若 agent 从未显式 respond，用最后一次 observation 的 payload 兜底
                if last_ok and "final_output" not in state.working_memory:
                    payload = getattr(observation, "payload", None)
                    if isinstance(payload, str):
                        state.working_memory["final_output"] = payload
                break

            if self._should_stop(decision, reflection, observation):
                state.status = "completed"
                break

        await self.hooks.trigger("on_complete", state)
        return self._summarize(state)

    async def _act_with_fallback(self, decision: StructuredDecision, state: TypedState) -> Any:
        """执行 action，未知 action_type 时走 FallbackActionHandler 降级。"""
        from lca.contracts.action import ActionRegistryProtocol

        try:
            return await self.body.act(decision, state)
        except ToolExecutionError as err:
            if not str(err).startswith("未注册的 action_type:"):
                raise
            # 从 body 中提取 action_registry 供降级使用
            registry = getattr(self.body, "action_registry", None)
            if registry is None or not isinstance(registry, ActionRegistryProtocol):
                raise
            return await self.fallback_handler.handle(decision, state, registry)

    def _should_stop(
        self,
        decision: StructuredDecision | None,
        reflection: Reflection | None,
        observation: Any = None,
    ) -> bool:
        if decision is None or reflection is None:
            return False
        if decision.action_type == "handoff":
            return True
        # 降级成功且 observation 为 success → 视为等价于 respond 完成
        is_degraded_success = (
            observation is not None
            and getattr(observation, "success", False)
            and FALLBACK_DEGRADATION_KEY in getattr(observation, "extra", {})
        )
        if decision.action_type == "respond" or is_degraded_success:
            return reflection.verdict != "needs_correction"
        return False

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
