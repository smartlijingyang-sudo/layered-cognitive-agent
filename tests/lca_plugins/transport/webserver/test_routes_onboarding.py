"""lca.plugins.transport.webserver.routes_onboarding —— /v1/onboarding/presets (ADR-0252 D7).

验证 RouteSpec 注册与公开常量。
"""

from __future__ import annotations

import pytest

from lca.plugins.transport.webserver.router.router import RouteRegistry


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[object, str]] = []

    def effect(self, dispose: object, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> object:
        assert key == "route_registry"
        return self._router

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.mark.asyncio
async def test_onboarding_route_registers() -> None:
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)
    assert "/v1/onboarding/presets" in router._exact
    assert len(ctx._fake_runtime.effects) == 1


def test_onboarding_route_exposes_public_constant() -> None:
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    assert {spec.path for spec in ROUTE_SPECS} == {"/v1/onboarding/presets"}
