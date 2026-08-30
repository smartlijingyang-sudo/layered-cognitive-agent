"""Profile-visible provider for the plan-bound perceive composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.perceive_composer import PerceiveComposer


class Config(BaseModel):
    """Strict configuration for the built-in perceive composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-perceive-composer",
    provides=["composer.perceive"],
    requires=[],
    implements=["AgentGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound perceive composer with a narrow context-and-state interface.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected perceive graph composer."""

    del config
    ctx.provide("composer.perceive", PerceiveComposer())


__all__ = ["Config", "setup"]
