"""Observability Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import ObservabilityBackend
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


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
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.capability.observability import ObservabilityService

    ctx.provide("observability", ObservabilityService())
