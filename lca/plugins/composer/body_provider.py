"""Profile-visible provider for the plan-bound execution composer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.composer.body_composer import BodyComposer


class Config(BaseModel):
    """Strict configuration for the built-in body composer provider."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-plan-body-composer",
    provides=["composer.body"],
    requires=[],
    implements=["AgentGraphComposer"],
    layer="L4",
    effects="none",
    description="Plan-bound execution composer with a narrow act-cluster interface.",
    test_suite="tests/composer/test_composer_consumes_compiled_capability.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide only the profile-selected execution graph composer."""

    del config
    ctx.provide("composer.body", BodyComposer())


__all__ = ["Config", "setup"]
