"""ModularBrain strategy plugin — Tier-3."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import BrainFactory
from lca.harness.plugin_api import PluginKind, plugin


@plugin(
    id="lca-brain-modular",
    provides=["brain_factory.modular"],
    requires=["gates", "critic.simple", "reasoner.prompt"],
    implements=[BrainFactory],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register the ModularBrain factory for lead-aware composition.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx: Any, config: Any) -> None:
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    gates = ctx.require("gates") if hasattr(ctx, "require") else ctx.inject("gates")
    factory = SimpleBrainFactory(
        agent_gate_factory=gates.assemble,
        critic_factory=ctx.inject("critic.simple"),
        reasoner_cls=ctx.inject("reasoner.prompt"),
    )
    ctx.provide("brain_factory.modular", factory)
