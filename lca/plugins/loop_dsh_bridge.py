"""DSH Bridge loop provider plugin — Tier-3 (alien loop driver)."""
from __future__ import annotations

from cordis import plugin


def _try_inject(ctx, key: str):
    """Try ctx.inject(key); return None on KeyError (cordis raises on missing)."""
    try:
        return ctx.inject(key)
    except KeyError:
        return None


@plugin(name="lca-loop-dsh-bridge")
async def setup(ctx, config) -> None:
    """Register DSH bridge loop at the dsh_bridge_loop key.

    session_store is optional — provided by session-persistence plugins
    in a real deployment. Falls back to in-memory if absent.
    """
    session_store = _try_inject(ctx, "session_store")

    def dsh_bridge_factory(store, inbox, identity_id, options, plugin_scope):
        raise NotImplementedError("Chunk 2 follow-up: DSH bridge loop factory")

    ctx.provide("dsh_bridge_loop", dsh_bridge_factory)
    if session_store is not None:
        ctx.provide("dsh_bridge_session_store", session_store)
