"""lca-gateway-routes-runs-sessions plugin — register /runs (8) + /v1/sessions (8)。

PR-7:把 ``/runs/{run_id}/profile`` 与 ``/runs/{run_id}/evidence/{ref}`` 从
``gateway.routes.build_routes`` 迁过来(build_routes 退役);route count
从 14 → 16。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.plugins.transport.webserver.router import RouteRegistry


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        assert key == "route_registry"
        return self._router

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.mark.asyncio
async def test_routes_runs_sessions_register_16_routes() -> None:
    """PR-7: /runs(8) + /v1/sessions(8) = 16。

    /runs 子树 8 条:
      /runs, /runs/{run_id}, /runs/{run_id}/live, /runs/{run_id}/doctor,
      /runs/{run_id}/profile, /runs/{run_id}/evidence/{ref:path},
      /runs/{run_id}/cancel, /runs/{run_id}/answer
    """
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(router._exact) == 16


@pytest.mark.asyncio
async def test_routes_runs_sessions_paths_match_migration_baseline() -> None:
    """迁移后路径覆盖迁移前 ``build_routes`` 的 /runs + /v1/sessions 子树。"""
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    expected_runs = {
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/live",
        "/runs/{run_id}/doctor",
        "/runs/{run_id}/profile",
        "/runs/{run_id}/evidence/{ref:path}",
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

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 16


def test_routes_runs_sessions_exposes_public_routes_constant() -> None:
    """ADR-0163 决策 5:``ROUTE_SPECS`` 是路径 catalog 的 SSOT,供 build_routes 退役后的测试/诊断直接 import。"""
    from lca.plugins.transport.webserver.routes_runs_sessions import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    paths = {spec.path for spec in ROUTE_SPECS}
    assert "/runs/{run_id}/profile" in paths
    assert "/runs/{run_id}/evidence/{ref:path}" in paths
