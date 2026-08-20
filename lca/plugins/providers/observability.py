"""Observability Provider plugin — Tier-2."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["console"])


@plugin(name="lca-observability-provider", inject=["observability"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.observability import create_observability

    if "console" in config.providers:
        ctx.inject("observability").register("console", lambda: create_observability("console"))
