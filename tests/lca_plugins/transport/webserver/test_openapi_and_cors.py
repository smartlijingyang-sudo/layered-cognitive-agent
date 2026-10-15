"""Tests for CORS preflight handling and the OpenAPI spec endpoint."""

from __future__ import annotations

import asyncio
from typing import Any

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.cors.cors import CORS_HEADERS
from lca.plugins.transport.webserver.handlers.openapi.spec import build_openapi_spec
from lca.plugins.transport.webserver.router.router import RouteRegistry


def test_cors_headers_cover_rest_verbs_and_user_header() -> None:
    methods = CORS_HEADERS["Access-Control-Allow-Methods"]
    for verb in ("GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"):
        assert verb in methods
    headers = CORS_HEADERS["Access-Control-Allow-Headers"]
    assert "x-lca-user-id" in headers
    assert "X-Lca-Token" in headers


def test_options_preflight_skips_auth_on_instrumented_patch_route() -> None:
    """PATCH profile 的 OPTIONS 预检必须不经认证返回 200 + CORS 头。"""
    from lca.plugins.transport.webserver.route.register import _instrument_route_handler
    from lca.plugins.transport.webserver.routes_1.routes_assistants.profile import (
        revise_assistant_profile,
    )

    app = Starlette(
        routes=[
            Route(
                "/v1/assistants/{assistant_id}/profile",
                _instrument_route_handler(
                    revise_assistant_profile,
                    path="/v1/assistants/{assistant_id}/profile",
                ),
                methods=["PATCH", "OPTIONS"],
            )
        ]
    )
    client = TestClient(app)
    resp = client.options(
        "/v1/assistants/asst_x/profile",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type,authorization,x-lca-user-id",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {}
    assert "PATCH" in resp.headers["access-control-allow-methods"]
    assert "x-lca-user-id" in resp.headers["access-control-allow-headers"]


def test_build_openapi_spec_lists_routes_and_security() -> None:
    async def _handler(_request: Any) -> JSONResponse:
        return JSONResponse({})

    routes = [
        Route("/runs", _handler, methods=["POST"]),
        Route("/runs/{run_id}", _handler, methods=["GET"]),
        Route("/health", _handler, methods=["GET"]),
    ]
    spec = build_openapi_spec(routes)

    assert spec["openapi"] == "3.0.3"
    assert spec["info"]["title"] == "LCA Agent Gateway API"
    assert set(spec["paths"]) == {"/runs", "/runs/{run_id}", "/health"}
    assert "post" in spec["paths"]["/runs"]
    assert "get" in spec["paths"]["/runs/{run_id}"]
    # 核心路径带手写 schema，其余路径回退通用 200。
    assert spec["paths"]["/runs"]["post"]["responses"]["202"]["description"] == "Run accepted"
    assert spec["paths"]["/health"]["get"]["responses"] == {"200": {"description": "OK"}}
    assert spec["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"
    assert spec["components"]["securitySchemes"]["UserIdHeader"]["name"] == "x-lca-user-id"
    assert spec["security"] == [{"BearerAuth": [], "UserIdHeader": []}]


def _build_registered_app() -> Starlette:
    """Assemble the runs-sessions route catalog the way production does."""
    from lca.plugins.transport.webserver.routes_2.routes_runs_sessions import (
        ROUTE_SPECS,
    )
    from lca.plugins.transport.webserver.routes_2.routes_runs_sessions import (
        setup as runs_sessions_setup,
    )

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

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    asyncio.run(runs_sessions_setup.setup(ctx, None))
    app = Starlette(routes=[])
    router.install(app)
    assert any(spec.path == "/v1/openapi.json" for spec in ROUTE_SPECS)
    return app


def test_openapi_json_endpoint_returns_valid_spec() -> None:
    app = _build_registered_app()
    client = TestClient(app)

    resp = client.get("/v1/openapi.json")
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"
    spec = resp.json()
    assert spec["openapi"] == "3.0.3"
    assert "/runs" in spec["paths"]
    assert "/v1/openapi.json" in spec["paths"]
    assert "/v1/runs/{run_id}/ws-token" in spec["paths"]
    assert "security" in spec


def test_openapi_json_options_preflight_returns_cors_headers() -> None:
    app = _build_registered_app()
    client = TestClient(app)

    resp = client.options(
        "/v1/openapi.json",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert (
        resp.headers["access-control-allow-methods"] == CORS_HEADERS["Access-Control-Allow-Methods"]
    )
