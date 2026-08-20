"""SimpleBrain strategy plugin — Tier-3 (default)."""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols import BrainFactory
from lca.plugins._cordis_adapter import PluginKind, plugin


@plugin(
    id="lca-brain-simple",
    provides=["brain_factory"],
    requires=["gates", "critic.simple", "reasoner.prompt"],
    implements=[BrainFactory],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register SimpleBrainFactory as the default brain_factory.",
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
    ctx.provide("brain_factory", factory)
