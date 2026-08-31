"""Gateway route catalog — every live route must be classified.

Replaces deploy.lobehub.stack surface matching. New routes without a
prefix here fail the test so they cannot silently appear unowned.

ADR-0115 thin factory: routes are installed by the lifespan via
``gateway_router.install(app)``; we drive the lifespan to enumerate.
"""

from __future__ import annotations

import asyncio
import re

from starlette.routing import Route, WebSocketRoute

from gateway.app import create_app

# Prefix / exact owners. Keep this list next to the routes plugins
# in lca/plugins/transport/webserver/.
SURFACES: tuple[tuple[str, str], ...] = (
    ("health", r"^/health$"),
    ("context", r"^/context$"),
    ("journal", r"^/journal"),
    ("runs", r"^/runs"),
    ("files", r"^/files"),
    ("sessions", r"^/v1/sessions"),
    ("openai", r"^/v1/"),
    ("devices", r"^/api/device"),
)


def _iter_paths(app) -> list[str]:
    paths: set[str] = set()
    for route in app.routes:
        if isinstance(route, (Route, WebSocketRoute)):
            if isinstance(route, Route) and route.methods == {"OPTIONS"}:
                continue
            paths.add(route.path)
    return sorted(paths)


def _paths_after_lifespan() -> list[str]:
    """Drive the Starlette lifespan so routes get installed."""
    app = create_app()

    async def _go() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(_go())
    return _iter_paths(app)


def test_every_live_route_has_an_owner() -> None:
    paths = _paths_after_lifespan()
    assert paths, "create_app() must expose routes after lifespan startup"
    compiled = [(name, re.compile(pattern)) for name, pattern in SURFACES]
    orphan = [
        path for path in paths if not any(pattern.search(path) for _name, pattern in compiled)
    ]
    assert orphan == [], f"add a SURFACES prefix for: {orphan}"


def test_known_prefixes_still_match_core_paths() -> None:
    paths = set(_paths_after_lifespan())
    assert "/health" in paths
    assert any(path.startswith("/runs") for path in paths)
    assert any(path.startswith("/v1/") for path in paths)
    assert any(path.startswith("/api/device") for path in paths)
