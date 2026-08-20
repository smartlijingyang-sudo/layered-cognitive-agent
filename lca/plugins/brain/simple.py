"""SimpleBrain strategy plugin — registers into BRAINS as 'default'."""

from __future__ import annotations

from typing import Any

from lca.contracts.capabilities import BRAINS
from lca.contracts.protocols import BrainFactory
from lca.harness.plugin_api import PluginKind, plugin


@plugin(
    id="lca-brain-simple",
    provides=[],
    requires=[BRAINS.key, "gates", "critic.simple", "reasoner.prompt"],
    implements=[BrainFactory],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="Register SimpleBrainFactory as brains['default'].",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx: Any, config: Any) -> None:
    del config
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    gates = ctx.require("gates") if hasattr(ctx, "require") else ctx.inject("gates")
    factory = SimpleBrainFactory(
        agent_gate_factory=gates.assemble,
        critic_factory=ctx.inject("critic.simple"),
        reasoner_cls=ctx.inject("reasoner.prompt"),
    )
    ctx.register(BRAINS.key, "default", factory)
