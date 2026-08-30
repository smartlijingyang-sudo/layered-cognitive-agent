"""Sandbox Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.runtime.infra import Sandbox
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(
    id="lca-sandbox-provider",
    requires=["sandbox"],
    implements=[Sandbox],
    layer="L0",
    effects="world",
    description="Register Sandbox providers on the SandboxService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.sandbox.factory import resolve_sandbox

    if "local" in config.providers:
        resolved = resolve_sandbox()
        if resolved is not None:
            ctx.require("sandbox").register("local", resolved, activate=True)
