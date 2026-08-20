"""File Store Provider plugin — Tier-2."""

from __future__ import annotations

from cordis import Context, plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(name="lca-file-store-provider", inject=["file_store"])
async def setup(ctx: Context, config: Config) -> None:
    from lca.layer0_infra.file_store import get_default_file_store

    if "local" in config.providers:
        ctx.inject("file_store").register("local", get_default_file_store())
