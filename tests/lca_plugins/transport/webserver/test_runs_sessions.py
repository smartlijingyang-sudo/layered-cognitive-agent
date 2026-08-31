"""lca-gateway-routes-runs-sessions plugin — register /runs (6) + /v1/sessions (8)。"""

from __future__ import annotations

from typing import Any

import pytest

from lca.plugins.transport.webserver.router import GatewayRouter


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: GatewayRouter) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        assert key == "gateway_router"
        return self._router

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.mark.asyncio
async def test_routes_runs_sessions_register_14_routes() -> None:
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    # /runs(6) + /v1/sessions(8) = 14
    assert len(router._exact) == 14


@pytest.mark.asyncio
async def test_routes_runs_sessions_paths_match_migration_baseline() -> None:
    """跟迁移前 gateway/app.py 的 /runs + /v1/sessions 路径一致(7 + 8 = 15,
    OPTIONS duplicate 已通过 methods=["POST","OPTIONS"] 合并到原 route)。"""
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    expected_runs = {
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/live",
        "/runs/{run_id}/doctor",
        "/runs/{run_id}/cancel",
        "/runs/{run_id}/answer",
    }
    expected_sessions = {
        "/v1/sessions",
        "/v1/sessions/{session_id}/messages",
        "/v1/sessions/{session_id}/snapshot",
        "/v1/sessions/{session_id}/events",
        "/v1/sessions/{session_id}/commands/answer",
        "/v1/sessions/{session_id}/commands/cancel",
        "/v1/sessions/{session_id}/commands/steer",
        "/v1/sessions/{session_id}/commands/inject",
    }
    assert expected_runs.issubset(router._exact.keys())
    assert expected_sessions.issubset(router._exact.keys())


@pytest.mark.asyncio
async def test_routes_runs_sessions_effects_tracked() -> None:
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 14