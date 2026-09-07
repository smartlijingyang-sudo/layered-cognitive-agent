"""Singleton factory for the agent runtime Redis client.

The agent runtime's stream is a single, well-known Redis instance —
the same one already in `lca-ops.yaml:42` for the LCA dev stack. This
factory reads the URL from the environment (LCA convention is to
honour `REDIS_URL` first, then `LCA_REDIS_URL`, then the dev default).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from redis.asyncio import Redis


def get_agent_runtime_redis_client() -> Redis:
    """Return the agent runtime Redis client.

    Order of precedence: ``REDIS_URL`` (native-compatible) →
    ``LCA_REDIS_URL`` (LCA-only) → ``redis://127.0.0.1:6379/0`` (LCA dev).
    The factory is intentionally a function (not a singleton) so tests
    can monkeypatch the env per-test.
    """
    url = os.environ.get("REDIS_URL") or os.environ.get("LCA_REDIS_URL") or "redis://127.0.0.1:6379/0"
    return aioredis.from_url(url, decode_responses=True)


__all__ = ("get_agent_runtime_redis_client",)
