"""Profile-selected TeamCaster provider for automatic Team casting.

The casting policy is independent of the gateway mode adapter and role catalog.
Profiles can replace this provider while retaining the same Team mode, observable
casting facts, and plan-to-Team translation.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.capabilities import TEAM_CASTER, TEAM_CASTING_PROMPT_RENDERER
from lca.contracts.protocols.casting import TeamCaster
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer4_app.casting import LLMTeamCaster


class Config(BaseModel):
    """The standard LLM Team caster needs no plugin configuration."""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca-team-caster-default",
    provides=[TEAM_CASTER.key],
    requires=[TEAM_CASTING_PROMPT_RENDERER.key],
    implements=[TeamCaster],
    layer="L4",
    effects="none",
    description="Provide the default LLM-backed Team casting policy.",
    Config=Config,
    test_suite="tests/test_gateway_team_factory.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the caster with its profile-selected prompt content policy."""

    del config
    renderer = ctx.require(TEAM_CASTING_PROMPT_RENDERER.key)
    ctx.provide(TEAM_CASTER.key, LLMTeamCaster(renderer))


__all__ = ["Config", "setup"]
