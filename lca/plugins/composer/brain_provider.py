"""Profile-visible provider for the plan-bound cognitive composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.brain_composer import BrainComposer


class Config(BaseModel):
    """Strict configuration for the built-in brain composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-brain-composer",
    provides=["composer.brain"],
    requires=[],
    implements=["AgentGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound cognitive composer with a narrow think-cluster interface.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected cognitive graph composer."""

    del config
    ctx.provide("composer.brain", BrainComposer())


__all__ = ["Config", "setup"]
