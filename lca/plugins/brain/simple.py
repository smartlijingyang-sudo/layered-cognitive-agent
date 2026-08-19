"""SimpleBrain strategy plugin — Tier-3 (default)."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-brain-simple")
async def setup(ctx, config) -> None:
    """Register the SimpleBrain (SimpleBrainFactory default) as 'simple'."""
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory()
    # SimpleBrainFactory is itself a factory — register itself as 'simple'
    factory.register("simple", factory)
    ctx.provide("brain_factory", factory)
