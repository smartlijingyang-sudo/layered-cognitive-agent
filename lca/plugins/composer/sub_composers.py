"""Profile-visible plan sub-composer provider."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.agent_assembly import PlanBoundAgentAssembler
from lca.plugins.composer.body_composer import BodyComposer
from lca.plugins.composer.brain_composer import BrainComposer
from lca.plugins.composer.perceive_composer import PerceiveComposer
from lca.plugins.composer.team_composer import TeamComposer


class Config(BaseModel):
    """Strict configuration for the built-in plan composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-sub-composers",
    provides=["composer.brain", "composer.body", "composer.perceive", "composer.team"],
    requires=[],
    implements=["AgentGraphComposer", "TeamGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound AgentGraph and TeamGraph composers with narrow interfaces.",
    test_suite="tests/application/test_spawn_bind_plan.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the complete set of plan composers to the booted Profile scope."""

    del config
    ctx.provide("composer.brain", BrainComposer())
    ctx.provide("composer.body", BodyComposer())
    ctx.provide("composer.perceive", PerceiveComposer())
    ctx.provide("composer.team", TeamComposer(PlanBoundAgentAssembler()))


__all__ = ["Config", "setup"]
