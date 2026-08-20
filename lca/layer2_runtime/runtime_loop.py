"""CognitiveRuntime —— 核心认知循环（ADR-0002 + PR5 + v3 §5.3）。

v3 闭环：
    Loop 只做编排：perceive → think → act → reflect → remember → stop。
    终止判定完全委托给 StopRule，业务逻辑零泄漏。

L2 层职责：
    将 Brain（认知）、Body（执行）、Memory（记忆）三大能力串联为可中断、
    可恢复、可观测的闭环。所有横切关注点（hook、checkpoint、error handling）
    在此层统一处理。

PR5 落地：
    - ``_emit`` 返回值被忽略（PR5 过渡门禁；PR10 拆除）
    - ``_sync_activated_skills`` → ``reducer.apply_activation``
    - ``perceive_hub: PerceiveHub`` 必填（生产路径注入；测试用 NullPerceiveHub）
    - StopRule 改为纯函数，final_output 走 ``StopDecision`` + ``apply_stop``
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
    PerceiveHub,
    Runtime,
    StateStore,
    StopRule,
)
from lca.layer0_infra.observability import get_span_context
from lca.layer0_infra.skills.activation_scope import get_newly_activated
from lca.layer2_runtime.completion.artifact_closure import synthesize_artifact_closure
from lca.layer2_runtime.hook_middleware import HOOK_SEAMS, middleware_bag

_log = structlog.get_logger("lca.runtime_loop")
_SEAM_TO_HOOK = dict(HOOK_SEAMS)


class _PhaseCtx:
    session_id = ""

    def record(self, event_data: object) -> None:
        return None


class CognitiveRuntime(Runtime):
    """核心认知循环实现（ADR-0002 + PR5）。

    v3 §5.3: ``perceive_hub: PerceiveHub`` 必填。L2 只依赖 Protocol，
    生产 Composer 必须注入真正的 Hub；测试可用 ``NullPerceiveHub``。
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
        middleware_registry: object | None = None,
    ) -> None:
        self.brain = brain
        self.body = body
        self.memory = memory
        self.hooks = hooks
        self.state_store = state_store
        self.stop_rule = stop_rule
        self.perceive_hub = perceive_hub
        self._mw = middleware_registry

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

    async def _emit(
        self, seam_key: str, phase: str, state: AgentState, ctx: _PhaseCtx
    ) -> AgentState:
        """Transitional hook bridge (PR5 → PR10).

        PR5: the return value is **discarded** by callers.  PR10 will
        remove the function entirely and replace it with protocol-boundary
        ``record()`` calls in Body.act / Brain.reflect.
        """
        if self._mw is not None:
            result = await self._mw.run(seam_key, phase, state, ctx)
            # PR5 transitional: callers ignore this return.  We return
            # the original state so legacy callers that DO assign still
            # see the same object — but the assignment is meaningless.
            return state if result is None else result
        hook_name = _SEAM_TO_HOOK.get(seam_key)
        if hook_name is None:
            return state
        bag = middleware_bag(state)
        kwargs = {
            key: bag[key]
            for key in ("decision", "observation", "reflection", "error")
            if key in bag
        }
        await self.hooks.trigger(hook_name, state, **kwargs)
        return state

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
        """执行 perceive → think → act → reflect 认知主循环（PR5 + v3 §5.3）。

        顺序：
            1. perceive — PerceiveHub 发射 ContextManifested（PR2 / PR3a）
            2. think    — Brain → Decision
            3. act      — Body → Observation（PR6 Envelope 注入）
            4. reflect  — Brain → Reflection
            5. remember — Memory.commit
            6. checkpoint — StateStore
            7. stop     — StopRule → StopDecision（纯函数，PR5）

        PR5：``_emit`` 返回值被忽略；``_sync_activated_skills`` → ``apply_activation``。
        """
        decision = observation = reflection = None
        for step in range(state.step, max_steps):
            state.step = step
            state.budget.used_steps = step
            try:
                ctx = _PhaseCtx()
                # PR5: ``_emit`` return is discarded (transitional until PR10).
                await self._emit("agent.pre_step", "step", state, ctx)
                # ── Phase 1: Perceive (PR3a — Hub is the SOLE emitter) ──
                await self._emit("agent.before_perceive", "perceive", state, ctx)
                manifest = await self.perceive_hub.perceive(state)
                state = _apply_manifest(state, manifest)
                await self._emit("agent.after_perceive", "perceive", state, ctx)
                # ── Phase 2: Think ──
                await self._emit("agent.before_think", "think", state, ctx)
                decision = await self.brain.think(state)
                middleware_bag(state)["decision"] = decision
                await self._emit("agent.after_think", "think", state, ctx)
                # ── Phase 3: Act ──
                await self._emit("agent.before_act", "act", state, ctx)
                observation = await self.body.act(decision, state)
                bag = middleware_bag(state)
                bag["decision"] = decision
                bag["observation"] = observation
                await self._emit("agent.after_act", "act", state, ctx)
                # ── Phase 3.5: Sync activation state (PR5) ──
                state = _apply_activation(state, _drain_newly_activated(state))
                # ── Phase 4: Reflect ──
                await self._emit("agent.before_reflect", "reflect", state, ctx)
                reflection = await self.brain.reflect(state, observation)
                middleware_bag(state)["reflection"] = reflection
                await self._emit("agent.after_reflect", "reflect", state, ctx)
                await self._emit("agent.before_turn_end", "turn_end", state, ctx)
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
            state = _apply_stop(state, stop)
            if stop.should_stop:
                if stop.reason == StopReason.BUDGET_EXCEEDED:
                    await self.hooks.trigger("on_error", state, error=BudgetExceededError())
                break
        await self.hooks.trigger("on_complete", state)
        self._apply_artifact_closure(state)
        return Result.from_state(state)

    @staticmethod
    def _apply_artifact_closure(state: AgentState) -> None:
        """Append workspace deliverables to final output (LobeHub workRegistration-style).

        Only auto-complete to COMPLETED when there is actual output (text or
        artifact closure).  A WORKING state with empty output stays WORKING
        so that Result.from_state can classify it as FAILED (zero-output guard).
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
        # No closure AND no output → leave status WORKING.  Result.from_state
        # will reclassify to FAILED with a diagnostic error.

    async def _checkpoint(
        self, state: AgentState, reason: SnapshotReason = SnapshotReason.PERIODIC
    ) -> StateSnapshot:
        snap = state.snapshot(reason=reason)
        ref = await self.state_store.save(state)
        snap.state_ref = ref
        return snap


def _drain_newly_activated(state: AgentState) -> tuple[ActivatedSkill, ...]:
    """Drain the contextvar activation scope into a tuple (PR5 helper).

    The state.activated_skills list is the authoritative read; newly
    activated skills (since the last sync) are returned for the caller
    to apply.
    """
    return tuple(
        ActivatedSkill(
            skill_id=s.skill_id,
            name=s.name,
            activated_at_step=state.step,
        )
        for s in get_newly_activated(state.activated_skills)
    )


def _apply_activation(state: AgentState, activated: tuple[ActivatedSkill, ...]) -> AgentState:
    """Reducer-style activation sync (PR5).

    Replaces ``_sync_activated_skills`` which mutated ``state`` directly.
    Returns the new state (AgentState is mutable dataclass; this function
    still touches ``state`` in place because that's how the existing tests
    exercise it — but the v3 ideal is a frozen Reducer; PR10 will convert).
    """
    if not activated:
        return state
    for skill in activated:
        state.activated_skills.append(skill)
    return state


def _apply_manifest(state: AgentState, manifest: object) -> AgentState:
    """Reduce a ``ContextManifest`` into state via the typed slot (PR3a).

    The Hub already wrote ``current_manifest`` into PerceiveState; this
    helper is the documented boundary for any future manifest-driven
    fields (e.g. tool pair anchors).
    """
    # PerceiveState.from_agent_state(state).current_manifest is already
    # set by the Hub; nothing else is folded here.
    return state


def _apply_stop(state: AgentState, stop: object) -> AgentState:
    """Reduce a ``StopDecision`` into state (PR5).

    The StopRule is pure (no AgentState mutation).  This function is the
    canonical writer of ``state.final_output`` and ``state.status`` from
    a stop decision — replaces the historical in-StopRule mutation that
    the spec forbids (§5.1).
    """
    if stop.status is not None:
        state.status = stop.status
    if stop.final_output is not None:
        state.final_output = stop.final_output
    return state
