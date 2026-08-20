"""Sandbox Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.contracts.protocols.infra import Sandbox
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(
    name="lca-sandbox-provider",
    requires=["sandbox"],
    implements=[Sandbox],
    layer="provider",
    side_effects="world",
    policy_class="control",
    description="Register Sandbox providers on the SandboxService Definition.",
    test_suite="tests/test_plugin_tree_single_owner.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer0_infra.sandbox.factory import resolve_sandbox

    if "local" in config.providers:
        resolved = resolve_sandbox()
        if resolved is not None:
            ctx.inject("sandbox").register("local", resolved, activate=True)
