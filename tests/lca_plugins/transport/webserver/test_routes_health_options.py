"""lca-gateway-routes-health-options plugin — register /health + OPTIONS.

ADR-0163 决策 3:``/journal/live`` is **optional** on the ``process_journal``
capability. When the capability is absent on the boot ``ctx``, the spec
is skipped and Starlette returns 404 for the path.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.plugins.transport.webserver.router import RouteRegistry


class _FakeRuntime:
    """Minimal cordis Context surface that supports ``effect(dispose, label=...)``."""

    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    """Minimal :class:`AuditedPluginContext` for plugin setup unit tests."""

    def __init__(
        self,
        router: RouteRegistry,
        *,
        capabilities: tuple[str, ...] = ("process_journal",),
    ) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()
        self._capabilities = set(capabilities)

    def require(self, key: str) -> Any:
        if key == "route_registry":
            return self._router
        if key in self._capabilities:
            return object()
        raise MissingCapabilityError(key)

    def inject(self, key: str, *, default: Any = None) -> Any:
        if key in self._capabilities:
            return object()
        return default

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.mark.asyncio
async def test_routes_health_options_register_three_routes() -> None:
    from lca.plugins.transport.webserver.routes_health_options import setup as plugin

    router = RouteRegistry()
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

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 3
    labels = {label for _dispose, label in ctx._fake_runtime.effects}
    assert "route:/health" in labels
    assert "route:/context" in labels
    assert "route:/journal/live" in labels


@pytest.mark.asyncio
async def test_routes_health_options_skips_journal_live_when_capability_missing() -> None:
    """ADR-0163 决策 3:``process_journal`` 缺失 → ``/journal/live`` 不挂。"""
    from lca.plugins.transport.webserver.routes_health_options import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router, capabilities=())  # explicit no capabilities
    await plugin.setup(ctx, None)

    assert "/health" in router._exact
    assert "/context" in router._exact
    assert "/journal/live" not in router._exact
    # Disposals reflect only the mounted routes.
    labels = {label for _dispose, label in ctx._fake_runtime.effects}
    assert "route:/journal/live" not in labels


def test_routes_health_options_exposes_public_routes_constant() -> None:
    """PR-7:``ROUTES`` 公开常量,供 ``build_routes`` 退役后的 catalog 校验。"""
    from lca.plugins.transport.webserver.routes_health_options import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    paths = {spec.path for spec in ROUTE_SPECS}
    assert paths == {"/health", "/context", "/journal/live"}
    # Optional capability gating is declared, not hidden in code paths.
    journal_live = next(s for s in ROUTE_SPECS if s.path == "/journal/live")
    assert "process_journal" in journal_live.optional
