"""ActionHandlerRegistry Seam Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-action-handler-registry-seam",
    provides=["action_handler_registry"],
    requires=[],
    implements=["ActionHandlerRegistry"],
    layer="L1",
    effects="none",
    description="Provide the ActionHandlerRegistry Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.action_handlers import InMemoryActionHandlerRegistry

    # 接缝只提供中性能力容器；默认 handler 由独立 provider 统一安装。
    ctx.provide("action_handler_registry", InMemoryActionHandlerRegistry())


__all__ = ["setup"]
