"""Sandbox Service Definition plugin — Tier-1."""

from __future__ import annotations
from typing import Any
from lca.contracts.protocols.infra import Sandbox
from lca.harness.plugin_api import plugin, PluginKind


@plugin(
    id="lca-sandbox-service",
    provides=["sandbox"],
    implements=[Sandbox],
    layer="L0",
    effects="world",
    description="Provide the Sandbox Definition service (ProviderDispatch + Sandbox Protocol).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.sandbox import SandboxService

    ctx.provide("sandbox", SandboxService())
