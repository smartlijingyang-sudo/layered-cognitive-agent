"""DeltaHandlerRegistry Seam Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-delta-handler-registry-seam",
    provides=["delta_handler_registry"],
    requires=[],
    implements=["DeltaHandlerRegistry"],
    layer="L2",
    effects="none",
    kind=PluginKind.SEAM,
    description="Provide the DeltaHandlerRegistry Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.delta_handler_registry import InMemoryDeltaHandlerRegistry

    # 接缝只提供中性能力容器；默认 handler 由独立 provider 统一安装。
    ctx.provide("delta_handler_registry", InMemoryDeltaHandlerRegistry())


__all__ = ["setup"]
