"""TeamHandle —— 封闭团队的运行句柄：策略即行为，句柄只是叙事边缘（ADR-0037）。

团队的一切编排决策在组合期已闭合进 ``TeamStrategy``；句柄运行期不编排，
只做三件事：bind 观测 hub → record 团队 run 容器（场景卡随事件投影）→
委派策略。span 拓扑由 OtelProjector 从 journal 生成，句柄不接触 span。
成员与 lead 以只读属性暴露，供组合无损性内省。
"""

from __future__ import annotations

import contextlib

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.message import AgentMessage, agent_message_as_text
from lca.contracts.models.core.result import Result
from lca.contracts.models.observability.journal import (
    TeamRunFinished,
    TeamRunStarted,
)
from lca.contracts.protocols import AgentUnit, TeamStrategy, TeamUnit
from lca.infrastructure.observability import (
    TEAM_CONTAINER_ROLE,
    BoundObservability,
    TeamTraceProfile,
    adopt_run_scope,
    bind_backends,
    objective_preview,
    plan_steps_joined,
    record,
    run_scope,
    set_session,
)


class TeamHandle(TeamUnit):
    """Holds a closed TeamStrategy + trace profile. Zero mutation on agents."""

    def __init__(
        self,
        strategy: TeamStrategy,
        profile: TeamTraceProfile,
        observability: BoundObservability,
        members: tuple[AgentUnit, ...],
        lead: AgentUnit | None = None,
        event_session_binder: object | None = None,
    ) -> None:
        self._strategy = strategy
        self._profile = profile
        self._observability = observability
        self.members = members
        self.lead = lead
        self._event_session_binder = event_session_binder

    async def run(self, objective: str | AgentMessage) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        set_session(self._profile.team_id)
        scope, _ = adopt_run_scope(role=TEAM_CONTAINER_ROLE)
        # PR-3.1: spine envelope for the agent_loop.iteration execution
        # point on the team entry. The team is a closed strategy; one
        # ``TeamHandle.run`` is one iteration (the cognitive loop sits
        # inside each member agent).
        from lca.plugins.events.publishers.spine_reflector_agent_spawn import (
            emit_agent_loop_iteration_end,
            emit_agent_loop_iteration_start,
        )

        iteration_trace_id = scope.trace_id
        iteration_role = f"team:{self._profile.team_id}"

        binder = self._event_session_binder
        bound_cm = (
            binder.bound(scope.run_id)  # type: ignore[union-attr]
            if binder is not None and hasattr(binder, "bound")
            else contextlib.nullcontext()
        )

        with bound_cm:
            return await self._run_body(
                text,
                scope,
                iteration_trace_id,
                iteration_role,
                emit_agent_loop_iteration_start,
                emit_agent_loop_iteration_end,
            )

    async def _run_body(
        self,
        text: str,
        scope: object,
        iteration_trace_id: str,
        iteration_role: str,
        emit_agent_loop_iteration_start: object,
        emit_agent_loop_iteration_end: object,
    ) -> Result:
        emit_agent_loop_iteration_start(  # type: ignore[operator]
            trace_id=iteration_trace_id,
            role=iteration_role,
            iteration_kind="fresh",
        )
        with bind_backends(self._observability), run_scope(scope):
            record(
                TeamRunStarted(
                    team_id=self._profile.team_id,
                    strategy_key=self._profile.strategy_key,
                    mandate=self._profile.mandate or "",
                    lead_role=self._profile.lead_role,
                    members=self._profile.member_roles,
                    objective=text,
                    objective_preview=objective_preview(text),
                    plan_steps=plan_steps_joined(self._profile.strategy_key, self._profile.mandate),
                )
            )
            # 默认 CANCELED：CancelledError 是 BaseException，不会进 except Exception。
            # finally 保证任何退出路径都发射 Finished，OTel attach 在同 task 配对 detach。
            finish_status = TaskStatus.CANCELED.value
            finish_output = ""
            finish_steps = 0
            finish_error = ""
            iteration_outcome: str = "success"
            try:
                result = await self._strategy.run(text)
                finish_status = (
                    result.status.value
                    if isinstance(result.status, TaskStatus)
                    else str(result.status)
                )
                finish_output = result.output or ""
                finish_steps = result.total_steps
                return result
            except Exception as err:
                finish_status = TaskStatus.FAILED.value
                finish_error = f"{type(err).__name__}: {err}"
                iteration_outcome = "failure"
                raise
            finally:
                record(
                    TeamRunFinished(
                        status=finish_status,
                        output_text=finish_output,
                        steps=finish_steps,
                        error=finish_error,
                    )
                )
                emit_agent_loop_iteration_end(
                    trace_id=iteration_trace_id,
                    role=iteration_role,
                    iteration_kind="fresh",
                    outcome=iteration_outcome,  # type: ignore[arg-type]
                )
