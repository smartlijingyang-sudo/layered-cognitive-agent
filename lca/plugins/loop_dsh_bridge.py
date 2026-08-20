"""DSH Bridge loop provider plugin — Tier-3 (alien loop driver)."""
from __future__ import annotations

from typing import Any

from cordis import Context, plugin


def _try_inject(ctx: Context, key: str) -> object | None:
    """Try ctx.inject(key); return None on KeyError (cordis raises on missing)."""
    try:
        return ctx.inject(key)
    except KeyError:
        return None


@plugin(name="lca-loop-dsh-bridge")
async def setup(ctx: Context, config: Any) -> None:
    """Register DSH bridge loop at the dsh_bridge_loop key.

    session_store is optional — provided by session-persistence plugins
    in a real deployment. Falls back to in-memory if absent.
    """
    session_store = _try_inject(ctx, "session_store")

    def dsh_bridge_factory(
        store: object,
        inbox: object,
        identity_id: str,
        options: dict[str, Any] | None,
        plugin_scope: object,
    ) -> object:
        raise NotImplementedError("Chunk 2 follow-up: DSH bridge loop factory")

    ctx.provide("dsh_bridge_loop", dsh_bridge_factory)
    if session_store is not None:
        ctx.provide("dsh_bridge_session_store", session_store)
