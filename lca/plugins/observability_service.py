"""Observability Service Definition plugin — Tier-1."""

from __future__ import annotations
from typing import Any
from lca.contracts.protocols import ObservabilityBackend
from lca.harness.plugin_api import plugin, PluginKind


@plugin(
    id="lca-observability-service",
    provides=["observability"],
    implements=[ObservabilityBackend],
    layer="L0",
    effects="none",
    description="Provide the Observability Definition service (ProviderDispatch + factory table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer0_infra.capability.observability import ObservabilityService

    ctx.provide("observability", ObservabilityService())
