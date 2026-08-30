"""EffectHandlerRegistry Seam Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-effect-handler-registry-seam",
    provides=["effect_handler_registry"],
    requires=[],
    implements=["EffectHandlerRegistry"],
    layer="L2",
    effects="none",
    description="Provide the EffectHandlerRegistry Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.effect_handlers import InMemoryEffectHandlerRegistry

    # A seam declares an empty capability container.  The separately enabled
    # provider plugin owns all default handler registration.
    ctx.provide("effect_handler_registry", InMemoryEffectHandlerRegistry())


__all__ = ["setup"]
