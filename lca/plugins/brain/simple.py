"""SimpleBrain strategy plugin — Tier-3 (default)."""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-brain-simple")
async def setup(ctx: Context, config: Any) -> None:
    """Register SimpleBrainFactory as the default 'brain_factory'."""
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory()
    ctx.provide("brain_factory", factory)
