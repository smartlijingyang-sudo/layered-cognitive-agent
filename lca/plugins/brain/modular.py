"""ModularBrain strategy plugin — Tier-3."""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-brain-modular")
async def setup(ctx: Context, config: Any) -> None:
    """Register the ModularBrain as 'modular' in the brain factory.

    The factory itself is a callable (SimpleBrainFactory) that returns a brain
    on demand. The plugin provides the default factory under 'brain_factory'.
    """
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory()
    ctx.provide("brain_factory", factory)
