"""TeamHandle —— 封闭团队的运行句柄：策略即行为，句柄只是叙事边缘（ADR-0037）。

团队的一切编排决策在组合期已闭合进 ``TeamStrategy``；句柄运行期不编排，
只做三件事：bind 观测 hub → record 团队 run 容器（场景卡随事件投影）→
委派策略。span 拓扑由 OtelProjector 从 journal 生成，句柄不接触 span。
成员与 lead 以只读属性暴露，供组合无损性内省。
"""

from __future__ import annotations

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.message import AgentMessage, agent_message_as_text
from lca.contracts.models.core.result import Result
from lca.contracts.models.observability.journal import RunScope, TeamRunFinished, TeamRunStarted
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
        scope = RunScope(trace_id=new_id("trace"), run_id=new_id("run"))
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
            result = await _run_with_closed_container(self._strategy, text)
            record(
                TeamRunFinished(
                    status=result.status,
                    output_preview=result.output or "",
                    steps=result.total_steps,
                )
            )
            return result


async def _run_with_closed_container(strategy: TeamStrategy, text: str) -> Result:
    """策略执行；异常路径补发失败收尾事件，保证 run 容器必闭（投影不泄漏）。"""
    try:
        return await strategy.run(text)
    except Exception as err:
        record(
            TeamRunFinished(status=TaskStatus.FAILED.value, error=f"{type(err).__name__}: {err}")
        )
        raise
