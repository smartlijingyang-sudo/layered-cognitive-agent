"""PromptReasoner plugin — Tier-3.

Stub: the reasoner is a component of ModularBrain, not a separate
plugin. This plugin exists to register the brain factory.
"""
from __future__ import annotations

from cordis import plugin


@plugin(name="lca-reasoner-prompt")
async def setup(ctx, config) -> None:
    """Stub — ModularBrain uses PromptReasoner internally; no separate ctx key."""
    pass
