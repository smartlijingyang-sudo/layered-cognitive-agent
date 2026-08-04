"""TeamOrchestrator — closed team handle; strategies only run."""

from __future__ import annotations

from lca.contracts.ids import new_id
from lca.contracts.message import AgentMessage, agent_message_as_text
from lca.contracts.protocols import AgentUnit, TeamContext, TeamStrategy, TeamUnit
from lca.contracts.result import Result
from lca.contracts.telemetry import (
    ATTR_LEAD_ROLE,
    ATTR_MANDATE,
    ATTR_MEMBERS,
    ATTR_OBJECTIVE_PREVIEW,
    ATTR_PLAN_STEPS,
    ATTR_STATUS,
    ATTR_STRATEGY_KEY,
    ATTR_TEAM_ID,
    SpanName,
)
from lca.layer0_infra.observability import NullObservability, bind, span
from lca.layer0_infra.observability.plan_narrative import plan_steps_joined

_OBJECTIVE_PREVIEW_MAX = 240


def _unit_role(unit: AgentUnit) -> str:
    profile = getattr(unit, "role_profile", None)
    role = getattr(profile, "role", None) if profile is not None else None
    return str(role) if role else "?"


class TeamOrchestrator(TeamUnit):
    """Holds a fully composed TeamContext + strategy. Zero mutation on agents."""

    def __init__(
        self,
        context: TeamContext,
        strategy: TeamStrategy,
    ) -> None:
        self._context = context
        self._strategy = strategy
        self.members = list(context.members)
        self.config = context.config
        self.lead = context.lead
        self.transport = context.transport
        self.teammates = list(context.teammates)
        self.team_id = context.team_id

    async def run(self, objective: str | object) -> Result:
        text = (
            agent_message_as_text(objective)
            if isinstance(objective, AgentMessage)
            else str(objective)
        )
        obs = self._context.observability or NullObservability()
        strategy_key = self._context.config.strategy_key if self._context.config is not None else ""
        mandate = (
            self._context.config.lead_mandate.value
            if self._context.config is not None and self._context.config.lead_mandate is not None
            else None
        )
        attrs: dict[str, object] = {
            ATTR_TEAM_ID: self.team_id,
            ATTR_STRATEGY_KEY: strategy_key,
        }
        if mandate is not None:
            attrs[ATTR_MANDATE] = mandate

        member_roles = [_unit_role(m) for m in self.members]
        lead_role = _unit_role(self.lead) if self.lead is not None else ""
        plan_attrs: dict[str, object] = {
            ATTR_TEAM_ID: self.team_id,
            ATTR_STRATEGY_KEY: strategy_key,
            ATTR_MEMBERS: ",".join(member_roles),
            ATTR_OBJECTIVE_PREVIEW: text[:_OBJECTIVE_PREVIEW_MAX],
            ATTR_PLAN_STEPS: plan_steps_joined(strategy_key, mandate),
        }
        if mandate is not None:
            plan_attrs[ATTR_MANDATE] = mandate
        if lead_role:
            plan_attrs[ATTR_LEAD_ROLE] = lead_role

        with bind(obs), span(SpanName.RUN_TEAM, trace_id=new_id("trace"), **attrs) as root:
            # Scenario card for console (and any sink) — first child of run.team
            with span(SpanName.RUN_PLAN, **plan_attrs):
                pass
            with span(SpanName.TEAM_STRATEGY, **{ATTR_STRATEGY_KEY: strategy_key}):
                result = await self._strategy.run(self._context, text)
            root.attributes[ATTR_STATUS] = result.status
            return result
