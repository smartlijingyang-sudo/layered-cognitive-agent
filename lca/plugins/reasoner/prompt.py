"""PromptReasoner plugin — Tier-3.

Stub: the reasoner is a component of ModularBrain, not a separate
plugin. This plugin exists to register the brain factory.
"""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-reasoner-prompt")
async def setup(ctx: Context, config: Any) -> None:
    """Stub — ModularBrain uses PromptReasoner internally; no separate ctx key."""
    pass
