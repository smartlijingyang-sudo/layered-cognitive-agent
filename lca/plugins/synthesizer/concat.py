"""ConcatSynthesizer plugin — Tier-3.

Stub: synthesizer is a component of ModularBrain, not a separate plugin.
"""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


@plugin(name="lca-synthesizer-concat")
async def setup(ctx: Context, config: Any) -> None:
    """Stub — ModularBrain uses ConcatSynthesizer internally; no separate ctx key."""
    pass
