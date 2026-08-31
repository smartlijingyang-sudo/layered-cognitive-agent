"""lca-gateway-routes-openai-compat-files — /v1/* + /files/* 路由(共 6 个)。"""

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
async def test_routes_openai_compat_files_register_six_routes() -> None:
    from lca.plugins.transport.webserver.routes_openai_compat_files import setup as plugin

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    # /v1/models + /v1/chat/completions + /v1/embeddings + /v1/responses + /files/{id} + /files/{id}/meta = 6
    assert len(router._exact) == 6


@pytest.mark.asyncio
async def test_routes_openai_compat_files_paths_match_baseline() -> None:
    from lca.plugins.transport.webserver.routes_openai_compat_files import setup as plugin

    router = GatewayRouter()
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

    router = GatewayRouter()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 6
