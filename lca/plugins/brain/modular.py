"""ModularBrain strategy plugin — Tier-3."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-brain-modular")
async def setup(ctx, config) -> None:
    """Register the ModularBrain strategy as 'modular' in the brain factory.

    The actual Brain class is imported lazily inside the factory call.
    """
    from lca.layer1_cognitive.brain.modular_brain import ModularBrain
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory()
    factory.register("modular", ModularBrain)
    ctx.provide("brain_factory", factory)
