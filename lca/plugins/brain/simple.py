"""SimpleBrain strategy plugin — Tier-3 (default)."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-brain-simple")
async def setup(ctx, config) -> None:
    """Register SimpleBrainFactory as the default 'brain_factory'."""
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory()
    ctx.provide("brain_factory", factory)
