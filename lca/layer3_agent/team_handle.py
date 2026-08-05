"""TeamHandle —— 封闭团队的运行句柄：策略即行为，句柄只是 trace 边缘（ADR-0034）。

团队的一切编排决策在组合期已闭合进 ``TeamStrategy``；句柄运行期不编排，
只做三件事：bind 观测 hub → 发 ``run.team`` / ``run.plan`` 场景卡 → 委派策略，
并打上状态。成员与 lead 以只读属性暴露，供组合无损性内省。
"""

from __future__ import annotations

from lca.contracts.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols import AgentUnit, TeamStrategy, TeamUnit
from lca.contracts.result import Result
from lca.contracts.telemetry import (
    ATTR_STATUS,
    ATTR_STRATEGY_KEY,
    EventName,
    SpanName,
)
from lca.layer0_infra.observability import (
    ObservabilityHub,
    TeamTraceProfile,
    bind,
    event,
    plan_card_attrs,
    set_session,
    span,
    team_run_attrs,
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
        with (
            bind(self._observability),
            span(SpanName.RUN_TEAM, **team_run_attrs(self._profile)) as root,
        ):
            # 场景卡（console 与一切后端的首个子节点）
            with span(SpanName.RUN_PLAN, **plan_card_attrs(self._profile, text)):
                pass
            with span(SpanName.TEAM_STRATEGY, **{ATTR_STRATEGY_KEY: self._profile.strategy_key}):
                result = await self._strategy.run(text)
            root.attributes[ATTR_STATUS] = result.status
            event(
                EventName.RUN_COMPLETED,
                **{ATTR_STATUS: result.status, "steps": result.total_steps},
            )
            return result
