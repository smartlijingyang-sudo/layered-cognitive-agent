"""CognitiveLoopFactory plugin — Tier-3 (loop driver)."""
from __future__ import annotations

import structlog
from cordis import plugin

_log = structlog.get_logger(__name__)


def build_cognitive_live_agent(
    store,
    inbox,
    identity_id: str,
    options: dict | None,
    plugin_scope,
):
    """Build a LiveAgent backed by the LCA cognitive loop."""
    # Full implementation deferred — placeholder for now
    raise NotImplementedError("Chunk 2 follow-up: cognitive loop factory")


@plugin(name="lca-loop-cognitive")
async def setup(ctx, config) -> None:
    """Register the cognitive loop builder at the agent_loop seam."""
    ctx.provide("agent_loop", build_cognitive_live_agent)
    _log.debug("cognitive_loop_registered", seam_key="agent_loop")
