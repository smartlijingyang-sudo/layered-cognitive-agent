"""Memory Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-memory-service",
    provides=["memory"],
    implements=["MemorySystem"],
    layer="service",
    side_effects="memory",
    policy_class="control",
    description="Provide the Memory Definition service (ProviderDispatch + factory table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.memory import MemoryService

    ctx.provide("memory", MemoryService())
