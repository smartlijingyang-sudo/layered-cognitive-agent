"""TeamHandle —— 封闭团队的运行句柄：策略即行为，句柄只是 trace 边缘（ADR-0034）。

团队的一切编排决策在组合期已闭合进 ``TeamStrategy``；句柄运行期不编排，
只做三件事：bind 观测 → 发 ``run.team`` / ``run.plan`` 场景卡 → 委派策略，
并打上状态。成员与 lead 以只读属性暴露，供组合无损性内省。
"""

from __future__ import annotations

from lca.contracts.ids import new_id
from lca.contracts.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols import AgentUnit, Observability, TeamStrategy, TeamUnit
from lca.contracts.result import Result
from lca.contracts.telemetry import ATTR_STATUS, ATTR_STRATEGY_KEY, SpanName
from lca.layer0_infra.observability import bind, span
from lca.layer0_infra.observability.team_trace import (
    TeamTraceProfile,
    plan_card_attrs,
    team_run_attrs,
)


class TeamHandle(TeamUnit):
    """Holds a closed TeamStrategy + trace profile. Zero mutation on agents."""

    def __init__(
        self,
        strategy: TeamStrategy,
        profile: TeamTraceProfile,
        observability: Observability,
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
        with (
            bind(self._observability),
            span(
                SpanName.RUN_TEAM, trace_id=new_id("trace"), **team_run_attrs(self._profile)
            ) as root,
        ):
            # Scenario card for console (and any sink) — first child of run.team
            with span(SpanName.RUN_PLAN, **plan_card_attrs(self._profile, text)):
                pass
            with span(SpanName.TEAM_STRATEGY, **{ATTR_STRATEGY_KEY: self._profile.strategy_key}):
                result = await self._strategy.run(text)
            root.attributes[ATTR_STATUS] = result.status
            return result
