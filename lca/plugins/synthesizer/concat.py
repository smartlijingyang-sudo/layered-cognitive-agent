"""ConcatSynthesizer plugin — Tier-3."""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-synthesizer-concat")
async def setup(ctx, config) -> None:
    """Register the ConcatSynthesizer as 'concat' in the brain factory."""
    from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer
    from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory

    factory = SimpleBrainFactory()
    factory.register_synthesizer("concat", ConcatSynthesizer)
    ctx.provide("brain_factory", factory)
