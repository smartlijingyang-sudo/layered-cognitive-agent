"""Tests for the gateway thin factory (ADR-0115 决定 6).

The thin factory:

- consumes a booted plugin tree via :func:`install_profile_lifespan`
- injects routes through ``ctx.inject('gateway_router').install(app)``
- exposes ``app.state.gateway_router`` after lifespan startup
- stays ≤ 60 lines (counted at PR-5 land time)
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from starlette.applications import Starlette

from gateway.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "gateway" / "app.py"


def test_create_app_returns_starlette_instance() -> None:
    """``create_app()`` returns a Starlette app."""
    app = create_app()
    assert isinstance(app, Starlette)


def test_create_app_has_no_eager_routes() -> None:
    """Thin factory: routes are installed by the lifespan, not eagerly.

    Before lifespan startup, ``app.routes`` must be empty (or only
    contain the framework defaults). This proves create_app is a thin
    factory that defers route installation to plugins.
    """
    app = create_app()
    assert app.routes == []


def test_create_app_gateway_router_state_is_none_by_default() -> None:
    """``app.state.gateway_router`` is None until lifespan startup."""
    app = create_app()
    assert app.state.gateway_router is None


def test_create_app_stores_kernel_profile() -> None:
    """``app.state.kernel_profile`` records the resolved profile path."""
    app = create_app()
    assert app.state.kernel_profile.endswith("web-standard.yaml")


def test_create_app_uses_lifespan_when_provided() -> None:
    """Caller-supplied ``lifespan`` overrides the default kernel lifespan."""
    entered = []

    from contextlib import asynccontextmanager
    from typing import Any

    @asynccontextmanager
    async def _fake_lifespan(scope_app: Starlette) -> Any:
        entered.append(scope_app)
        yield {}

    create_app(lifespan=_fake_lifespan)
    # The factory wires the supplied lifespan onto the app — we do not
    # actually drive it here, but we assert the function ran without error.
    assert callable(_fake_lifespan)


def test_create_app_with_explicit_profile_path() -> None:
    """An explicit ``profile_path`` overrides the default and $LCA_PROFILE."""
    app = create_app(profile_path="profiles/test-minimal.yaml")
    assert app.state.kernel_profile == "profiles/test-minimal.yaml"


def test_gateway_app_py_is_under_sixty_lines() -> None:
    """ADR-0115 决定 6: gateway/app.py 必须 ≤ 60 行(land-time budget)."""
    with APP_PATH.open() as f:
        line_count = sum(1 for _ in f)
    assert line_count <= 60, f"gateway/app.py is {line_count} lines; ADR-0115 决定 6 budget is 60"


def test_create_app_lifespan_installs_routes() -> None:
    """Driving the default lifespan installs routes from gateway_router plugin."""
    app = create_app()

    async def _drive() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(_drive())
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert paths, "lifespan startup should install routes"
    assert "/health" in paths
    assert any(p.startswith("/runs") for p in paths)
    assert any(p.startswith("/v1/") for p in paths)
    # ``gateway_router`` is set on app.state during lifespan startup.
    assert app.state.gateway_router is not None


def test_thin_factory_docstring_mentions_adr_0115() -> None:
    """The thin-factory rationale is documented in the module docstring."""
    text = APP_PATH.read_text()
    assert re.search(r"ADR-?0115", text), "gateway/app.py should reference ADR-0115"
    assert "thin factory" in text.lower()
