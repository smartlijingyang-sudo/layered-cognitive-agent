"""ModularBrain strategy plugin — Tier-3."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-brain-modular")
async def setup(ctx, config) -> None:
    """Register the ModularBrain as 'modular' in the brain factory.

    The factory itself is a callable (SimpleBrainFactory) that returns a brain
    on demand. The plugin provides the default factory under 'brain_factory'.
    """
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory()
    ctx.provide("brain_factory", factory)
