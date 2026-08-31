"""lca-gateway-routes-health-options plugin — register /health + OPTIONS."""

from __future__ import annotations

from typing import Any

import pytest

from lca.plugins.transport.webserver.router import GatewayRouter


class _FakeRuntime:
    """Minimal cordis Context surface that supports ``effect(dispose, label=...)``."""

    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    """Minimal :class:`AuditedPluginContext` for plugin setup unit tests."""

    def __init__(self, router: GatewayRouter) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        assert key == "gateway_router"
        return self._router

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.mark.asyncio
async def test_routes_health_options_register_three_routes() -> None:
    from lca.plugins.transport.webserver.routes_health_options import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    # /health + /context + /journal/live = 3
    assert len(router._exact) == 3
    assert "/health" in router._exact
    assert "/context" in router._exact
    assert "/journal/live" in router._exact


@pytest.mark.asyncio
async def test_routes_health_options_effects_tracked() -> None:
    from lca.plugins.transport.webserver.routes_health_options import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 3
    labels = {label for _dispose, label in ctx._fake_runtime.effects}
    assert "route:/health" in labels
    assert "route:/context" in labels
    assert "route:/journal/live" in labels


def test_routes_health_options_exposes_public_routes_constant() -> None:
    """PR-7:``ROUTES`` 公开常量,供 ``build_routes`` 退役后的 catalog 校验。"""
    from lca.plugins.transport.webserver.routes_health_options import ROUTES

    assert isinstance(ROUTES, tuple)
    paths = {r.path for r in ROUTES}
    assert paths == {"/health", "/context", "/journal/live"}
