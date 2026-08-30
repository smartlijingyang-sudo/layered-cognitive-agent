"""Sandbox Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.infra import Sandbox
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


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
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.capability.sandbox import SandboxService

    ctx.provide("sandbox", SandboxService())
