"""Memory Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-memory-service",
    provides=["memory"],
    implements=["MemorySystem"],
    layer="L0",
    effects="memory",
    description="Provide the Memory Definition service (ProviderDispatch + factory table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.capability.memory import MemoryService

    ctx.provide("memory", MemoryService())
