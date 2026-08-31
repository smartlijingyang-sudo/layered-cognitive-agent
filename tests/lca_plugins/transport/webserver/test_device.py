"""lca-gateway-routes-device — /api/device/* (7 HTTP) + /api/device/ws (1 WS)。"""

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
async def test_routes_device_register_seven_http_routes() -> None:
    from lca.plugins.transport.webserver.routes_device import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(router._exact) == 7


@pytest.mark.asyncio
async def test_routes_device_register_one_websocket() -> None:
    from lca.plugins.transport.webserver.routes_device import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(router._upgrades) == 1
    assert "/api/device/ws" in router._upgrades


@pytest.mark.asyncio
async def test_routes_device_paths_match_baseline() -> None:
    from lca.plugins.transport.webserver.routes_device import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    expected = {
        "/api/device/status",
        "/api/device/devices",
        "/api/device/tool-call",
        "/api/device/system-info",
        "/api/device/rpc",
        "/api/device/agent/run",
        "/api/device/files/upload",
    }
    assert expected.issubset(router._exact.keys())


@pytest.mark.asyncio
async def test_routes_device_effects_tracked() -> None:
    """8 routes × 1 effect each = 8 effects(7 HTTP + 1 WS)。"""
    from lca.plugins.transport.webserver.routes_device import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 8
    labels = {label for _dispose, label in ctx._fake_runtime.effects}
    assert "ws:/api/device/ws" in labels
