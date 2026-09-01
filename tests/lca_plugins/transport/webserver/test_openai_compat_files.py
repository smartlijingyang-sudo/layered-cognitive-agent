"""lca-gateway-routes-openai-compat-files — /v1/* + /files/* 路由(共 6 个)。"""

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
        self._capabilities = {"route_registry", "llm_resolver"}

    def require(self, key: str) -> Any:
        if key == "route_registry":
            return self._router
        if key in self._capabilities:
            return object()
        raise AssertionError(f"unexpected required capability {key!r}")

    def inject(self, key: str, *, default: Any = None) -> Any:
        if key in self._capabilities:
            return object()
        return default

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.mark.asyncio
async def test_routes_openai_compat_files_register_six_routes() -> None:
    from lca.plugins.transport.webserver.routes_openai_compat_files import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    # /v1/models + /v1/chat/completions + /v1/embeddings + /v1/responses + /files/{id} + /files/{id}/meta = 6
    assert len(router._exact) == 6


@pytest.mark.asyncio
async def test_routes_openai_compat_files_paths_match_baseline() -> None:
    from lca.plugins.transport.webserver.routes_openai_compat_files import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    expected = {
        "/v1/models",
        "/v1/chat/completions",
        "/v1/embeddings",
        "/v1/responses",
        "/files/{attachment_id}",
        "/files/{attachment_id}/meta",
    }
    assert expected.issubset(router._exact.keys())


@pytest.mark.asyncio
async def test_routes_openai_compat_files_effects_tracked() -> None:
    from lca.plugins.transport.webserver.routes_openai_compat_files import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 6
