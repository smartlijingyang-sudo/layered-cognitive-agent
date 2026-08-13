"""TeamHandle —— 封闭团队的运行句柄：策略即行为，句柄只是叙事边缘（ADR-0037）。

团队的一切编排决策在组合期已闭合进 ``TeamStrategy``；句柄运行期不编排，
只做三件事：bind 观测 hub → record 团队 run 容器（场景卡随事件投影）→
委派策略。span 拓扑由 OtelProjector 从 journal 生成，句柄不接触 span。
成员与 lead 以只读属性暴露，供组合无损性内省。
"""

from __future__ import annotations

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.message import AgentMessage, agent_message_as_text
from lca.contracts.models.core.result import Result
from lca.contracts.models.observability.journal import (
    TEAM_CONTAINER_ROLE,
    TeamRunFinished,
    TeamRunStarted,
    adopt_run_scope,
)
from lca.contracts.protocols import AgentUnit, TeamStrategy, TeamUnit
from lca.layer0_infra.observability import (
    ObservabilityHub,
    TeamTraceProfile,
    bind,
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
        observability: ObservabilityHub,
        members: tuple[AgentUnit, ...],
        lead: AgentUnit | None = None,
    ) -> None:
        self._strategy = strategy
        self._profile = profile
        self._observability = observability
        self.members = members
        self.lead = lead

    async def run(self, objective: str | AgentMessage) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        set_session(self._profile.team_id)
        scope, _ = adopt_run_scope(role=TEAM_CONTAINER_ROLE)
        with bind(self._observability), run_scope(scope):
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
