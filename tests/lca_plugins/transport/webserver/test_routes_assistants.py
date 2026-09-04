"""lca.plugins.transport.webserver.routes_assistants — /v1/assistants (PR-5).

Test the registry surface (6 routes) and the COMPAT 501 envelope used
while PR-3 catalog plugin is absent. The handler bodies must remain
"fail-closed 4xx" (ADR-0187 §3 D7) but never crash the registry boot.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.router import RouteRegistry


class _FakeRuntime:
    """Minimal cordis Context surface that supports effect()."""

    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    """Minimal :class:`AuditedPluginContext` for plugin setup unit tests."""

    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> Any:
        assert key == "route_registry"
        return self._router

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


def _setup_plugin() -> tuple[Any, RouteRegistry]:
    """Run the routes_assistants setup with a fake ctx and return the router.

    Returns the cordis plugin instance (for manifest assertions) and the
    populated :class:`RouteRegistry`.
    """
    from lca.plugins.transport.webserver.routes_assistants import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    return plugin, router, ctx


@pytest.mark.asyncio
async def test_routes_assistants_register_five_routes() -> None:
    """Five :class:`RouteSpec` entries; ``/v1/assistants`` carries
    both POST (create) and GET (list) via the dispatcher."""
    plugin, router, ctx = _setup_plugin()
    await plugin.setup(ctx, None)
    assert len(router._exact) == 5


@pytest.mark.asyncio
async def test_routes_assistants_paths_match_advertised_surface() -> None:
    plugin, router, ctx = _setup_plugin()
    await plugin.setup(ctx, None)
    expected = {
        "/v1/assistants",
        "/v1/assistants/{assistant_id}",
        "/v1/assistants/{assistant_id}/profile",
        "/v1/assistants/{assistant_id}/skills:install",
        "/v1/assistants/{assistant_id}/retire",
    }
    assert expected.issubset(router._exact.keys())


@pytest.mark.asyncio
async def test_routes_assistants_effects_tracked() -> None:
    plugin, _router, ctx = _setup_plugin()
    await plugin.setup(ctx, None)
    assert len(ctx._fake_runtime.effects) == 5
    labels = {label for _dispose, label in ctx._fake_runtime.effects}
    for path in (
        "/v1/assistants",
        "/v1/assistants/{assistant_id}",
        "/v1/assistants/{assistant_id}/profile",
        "/v1/assistants/{assistant_id}/skills:install",
        "/v1/assistants/{assistant_id}/retire",
    ):
        assert f"route:{path}" in labels


def test_routes_assistants_exposes_public_routes_constant() -> None:
    from lca.plugins.transport.webserver.routes_assistants import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    paths = {spec.path for spec in ROUTE_SPECS}
    assert paths == {
        "/v1/assistants",
        "/v1/assistants/{assistant_id}",
        "/v1/assistants/{assistant_id}/profile",
        "/v1/assistants/{assistant_id}/skills:install",
        "/v1/assistants/{assistant_id}/retire",
    }


# ── 501 COMPAT envelope behavior ──────────────────────────────────────


def _app_with_routes(router: RouteRegistry) -> Starlette:
    """Materialise a Starlette app with the registered routes (catalog absent)."""
    app = Starlette()
    router.install(app)
    return app


def _run_plugin_setup(plugin: Any, ctx: Any) -> None:
    """Drive the async setup from a sync test."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():
        # In a pytest-asyncio context — fall back to awaiting directly.
        return _await_setup(plugin, ctx)
    loop.run_until_complete(plugin.setup(ctx, None))


def _await_setup(plugin: Any, ctx: Any) -> None:
    import asyncio

    return asyncio.get_event_loop().run_until_complete(plugin.setup(ctx, None))


def test_post_assistants_returns_501_when_catalog_missing() -> None:
    """POST /v1/assistants with no catalog → 501 + COMPAT marker."""
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.post("/v1/assistants", json={"name": "demo"})
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "catalog_unavailable"
    assert "COMPAT" in body["error"]["marker"]
    assert "assistant.catalog plugin present" in body["error"]["marker"]


def test_get_assistants_returns_501_when_catalog_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.get("/v1/assistants")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "catalog_unavailable"


def test_get_assistant_by_id_returns_501_when_catalog_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.get("/v1/assistants/asst_1")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "catalog_unavailable"


def test_patch_assistant_profile_returns_501_when_catalog_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.patch("/v1/assistants/asst_1/profile", json={"description": "x"})
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "catalog_unavailable"


def test_install_skill_returns_501_when_overlay_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.post("/v1/assistants/asst_1/skills:install", json={"source": "url:foo"})
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "catalog_unavailable"


def test_retire_assistant_returns_501_when_catalog_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.post("/v1/assistants/asst_1/retire", json={"reason": "x"})
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "catalog_unavailable"


# ── Plugin manifest / ADR contract ────────────────────────────────────


def test_routes_assistants_plugin_id_convention() -> None:
    """ADR-0187 §3 D6 plugin module id must align with the dir hierarchy."""
    from lca.plugins.transport.webserver.routes_assistants import setup as plugin

    defn = plugin._lca_definition
    assert defn.id == "lca.plugins.transport.webserver.routes_assistants"


def test_routes_assistants_plugin_does_not_require_catalog_at_boot() -> None:
    """I-A10: web-standard profile must remain mountable without the catalog.

    The plugin declares only ``route_registry`` as a hard requirement;
    catalog / overlay are looked up dynamically via ``app.state`` so the
    plugin stays mountable on profiles that do not opt into
    ``assistant-runtime``.
    """
    from lca.plugins.transport.webserver.routes_assistants import setup as plugin

    defn = plugin._lca_definition
    required = set(defn.required_capability_keys)
    assert required == {"route_registry"}
    assert "assistant.catalog" not in required
    assert "assistant.skill_overlay" not in required


def test_routes_assistants_provides_route_seam() -> None:
    """Plugin provides ``webserver.routes.assistants`` capability."""
    from lca.plugins.transport.webserver.routes_assistants import setup as plugin

    defn = plugin._lca_definition
    provided = set(defn.provided_capability_keys)
    assert "webserver.routes.assistants" in provided


# ── Marker / COMPAT hygiene ───────────────────────────────────────────


def test_not_implemented_marker_carries_delete_when() -> None:
    """The COMPAT marker must carry a delete-when condition (AGENTS.md §1)."""
    from lca.plugins.transport.webserver.routes_assistants import (
        _ASSISTANT_NOT_IMPLEMENTED_MARKER,
    )

    assert "COMPAT" in _ASSISTANT_NOT_IMPLEMENTED_MARKER
    assert "delete-when" in _ASSISTANT_NOT_IMPLEMENTED_MARKER
    assert "assistant.catalog" in _ASSISTANT_NOT_IMPLEMENTED_MARKER


def test_handlers_tolerate_missing_state() -> None:
    """Handler bodies must not crash when ``request.app.state`` is absent.

    The catalog probe via :func:`_catalog_from_request` returns ``None``
    for objects that don't expose ``app.state`` (e.g. plain ASGI scopes
    during early boot / dry-run); handlers then short-circuit to 501.
    """
    from lca.plugins.transport.webserver.routes_assistants import (
        _catalog_from_request,
        _skill_overlay_from_request,
    )

    class _Bare:
        pass

    bare = _Bare()
    assert _catalog_from_request(bare) is None  # type: ignore[arg-type]
    assert _skill_overlay_from_request(bare) is None  # type: ignore[arg-type]


def test_helpers_use_app_state_when_present() -> None:
    """When ``app.state`` carries the catalog, the helper returns it."""
    from lca.plugins.transport.webserver.routes_assistants import (
        _catalog_from_request,
        _skill_overlay_from_request,
    )

    class _State:
        assistant_catalog = "catalog-handle"
        assistant_skill_overlay = "overlay-handle"

    class _App:
        state = _State()

    class _Bare:
        app = _App()

    assert _catalog_from_request(_Bare()) == "catalog-handle"
    assert _skill_overlay_from_request(_Bare()) == "overlay-handle"


# ── Sentinel: ensure handlers are imported and callable ───────────────


def test_handlers_are_coroutine_callables() -> None:
    """Sanity: each exported handler is an async coroutine function."""
    import inspect

    from lca.plugins.transport.webserver.routes_assistants import (
        create_assistant,
        get_assistant,
        install_assistant_skill,
        list_assistants,
        retire_assistant,
        revise_assistant_profile,
    )

    for fn in (
        create_assistant,
        list_assistants,
        get_assistant,
        revise_assistant_profile,
        install_assistant_skill,
        retire_assistant,
    ):
        assert inspect.iscoroutinefunction(fn), f"{fn.__name__} must be async"
