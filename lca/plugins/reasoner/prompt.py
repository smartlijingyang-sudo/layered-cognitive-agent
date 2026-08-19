"""PromptReasoner plugin — Tier-3."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-reasoner-prompt")
async def setup(ctx, config) -> None:
    """Register the PromptReasoner as 'prompt' in the brain factory."""
    from lca.layer1_cognitive.brain.reasoner import PromptReasoner
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory()
    factory.register_reasoner("prompt", PromptReasoner)
    ctx.provide("brain_factory", factory)
