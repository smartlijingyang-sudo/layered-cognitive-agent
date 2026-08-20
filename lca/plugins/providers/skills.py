"""Skills Provider plugin — Tier-2."""
from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["disk"])


@plugin(name="lca-skills-provider", inject=["skills"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.skills.factory import resolve_skill_store

    if "disk" in config.providers:
        ctx.inject("skills").register("disk", resolve_skill_store())
