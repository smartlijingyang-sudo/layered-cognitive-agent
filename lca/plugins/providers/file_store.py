"""File Store Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(
    id="lca-file-store-provider",
    requires=["file_store"],
    layer="L0",
    effects="world",
    description="Register FileStore providers on the FileStoreService Definition.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.file_store import get_default_file_store

    if "local" in config.providers:
        ctx.inject("file_store").register("local", get_default_file_store())
