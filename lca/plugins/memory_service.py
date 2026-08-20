"""Memory Service Definition plugin — Tier-1."""

from __future__ import annotations
from typing import Any
from lca.harness.plugin_api import plugin, PluginKind


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
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.memory import MemoryService

    ctx.provide("memory", MemoryService())
