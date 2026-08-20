"""Sandbox Service Definition plugin — Tier-1."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols.infra import Sandbox
from lca.plugins._cordis_adapter import plugin


@plugin(
    name="lca-sandbox-service",
    provides=["sandbox"],
    implements=[Sandbox],
    layer="service",
    side_effects="world",
    policy_class="control",
    description="Provide the Sandbox Definition service (ProviderDispatch + Sandbox Protocol).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.sandbox import SandboxService

    ctx.provide("sandbox", SandboxService())
