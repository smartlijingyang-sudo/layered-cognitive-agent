"""Plan-driven L4 sub-composer provider.

The provider exposes the four composition capabilities consumed by
``spawn_bind_plan``.  They are ordinary profile plugins: their identity and
availability are visible in the resolved capability graph rather than being
implicit fallbacks in the L4 composition root.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.legacy_sub_composers import (
    BodyComposer,
    BrainComposer,
    PerceiveComposer,
    TeamComposer,
)


class Config(BaseModel):
    """Strict configuration for the built-in sub-composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-sub-composers",
    provides=["composer.brain", "composer.body", "composer.perceive", "composer.team"],
    requires=[],
    implements=["Composer"],
    layer="L4",
    effects="none",
    description="Profile-visible sub-composers for CompiledRunPlan binding",
    test_suite="tests/layer4_app/test_spawn_bind_plan.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the four stateless sub-composers to a booted profile scope."""

    ctx.provide("composer.brain", BrainComposer())
    ctx.provide("composer.body", BodyComposer())
    ctx.provide("composer.perceive", PerceiveComposer())
    ctx.provide("composer.team", TeamComposer())


__all__ = ["Config", "setup"]
