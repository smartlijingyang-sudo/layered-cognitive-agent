"""Tools Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-tools-service",
    provides=["tools"],
    requires=[],
    implements=["ToolRegistry"],
    layer="L0",
    effects="tools",
    description="Provide the Tool registry Definition service (forked per-run).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.capability.tools import ToolsService

    ctx.provide("tools", ToolsService())
