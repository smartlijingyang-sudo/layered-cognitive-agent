"""ReplayLoopFactory plugin — Tier-3 (deterministic replay from journal)."""
from __future__ import annotations

from cordis import plugin


def _try_inject(ctx, key: str):
    """Try ctx.inject(key); return None on KeyError (cordis raises on missing)."""
    try:
        return ctx.inject(key)
    except KeyError:
        return None


@plugin(name="lca-loop-replay")
async def setup(ctx, config) -> None:
    """Register replay loop at the agent_loop seam.

    session_store is optional — may be None. The replay loop falls back
    to in-memory when session_store is not provided.
    """
    session_store = _try_inject(ctx, "session_store")

    def replay_loop_factory(store, inbox, identity_id, options, plugin_scope):
        raise NotImplementedError("Chunk 2 follow-up: replay loop factory")

    ctx.provide("agent_loop", replay_loop_factory)
    if session_store is not None:
        ctx.provide("replay_session_store", session_store)
