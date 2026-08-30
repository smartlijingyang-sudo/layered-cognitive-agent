"""GateChainComposer Seam Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-gate-chain-composer-seam",
    provides=["gate_chain_composer"],
    requires=[],
    implements=["GateChainComposer"],
    layer="L1",
    effects="none",
    kind=PluginKind.SEAM,
    description="Provide the GateChainComposer Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.gate.gate_chain_composer import DefaultGateChainComposer

    ctx.provide("gate_chain_composer", DefaultGateChainComposer())


__all__ = ["setup"]
