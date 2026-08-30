"""Profile-visible provider for the plan-bound organization composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.collaboration.team_composer import TeamComposer
from lca.plugins.composer.composition.agent_assembly import PlanBoundAgentAssembler


class Config(BaseModel):
    """Strict configuration for the built-in team composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-team-composer",
    provides=["composer.team"],
    requires=[],
    implements=["TeamGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound organization composer with a narrow team-graph interface.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected organization graph composer."""

    del config
    ctx.provide("composer.team", TeamComposer(PlanBoundAgentAssembler()))


__all__ = ["Config", "setup"]
