"""File store Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-file-store-service",
    provides=["file_store"],
    implements=[],
    layer="L0",
    effects="world",
    description="Provide the FileStore Definition service (ProviderDispatch + file-store table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.capability.files import FileStoreService

    service = FileStoreService()
    ctx.provide("file_store", service)
