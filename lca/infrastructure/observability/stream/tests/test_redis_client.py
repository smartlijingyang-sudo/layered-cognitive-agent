"""Verify the Redis client factory reads the dev default."""
from redis.asyncio import Redis

from lca.infrastructure.observability.stream.redis_client import get_agent_runtime_redis_client


def test_default_url_is_127_0_0_1_6379(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("LCA_REDIS_URL", raising=False)
    client = get_agent_runtime_redis_client()
    assert isinstance(client, Redis)
    # async client; verify the connection info via private attributes
    conn = client.connection_pool.connection_kwargs
    assert conn["host"] == "127.0.0.1"
    assert int(conn["port"]) == 6379


def test_reddis_url_env_overrides(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis.internal:6380/2")
    client = get_agent_runtime_redis_client()
    conn = client.connection_pool.connection_kwargs
    assert conn["host"] == "redis.internal"
    assert int(conn["port"]) == 6380
    assert int(conn["db"]) == 2
