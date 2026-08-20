"""Sandbox Provider plugin — Tier-2."""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(name="lca-sandbox-provider", inject=["sandbox"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.sandbox.factory import resolve_sandbox

    if "local" in config.providers:
        resolved = resolve_sandbox()
        if resolved is not None:
            ctx.inject("sandbox").register("local", resolved, activate=True)
