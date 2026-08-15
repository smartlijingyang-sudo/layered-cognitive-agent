"""Gateway route catalog — every live route must be classified.

Replaces deploy.lobehub.stack surface matching. New routes without a
prefix here fail the test so they cannot silently appear unowned.
"""

from __future__ import annotations

import re

from starlette.routing import Route, WebSocketRoute

from gateway.app import create_app

# Prefix / exact owners. Keep this list next to gateway.app:create_app.
SURFACES: tuple[tuple[str, str], ...] = (
    ("health", r"^/health$"),
    ("context", r"^/context$"),
    ("journal", r"^/journal"),
    ("runs", r"^/runs"),
    ("files", r"^/files"),
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


def test_every_live_route_has_an_owner() -> None:
    paths = _iter_paths(create_app())
    assert paths, "create_app() must expose routes"
    compiled = [(name, re.compile(pattern)) for name, pattern in SURFACES]
    orphan = [
        path for path in paths if not any(pattern.search(path) for _name, pattern in compiled)
    ]
    assert orphan == [], f"add a SURFACES prefix for: {orphan}"


def test_known_prefixes_still_match_core_paths() -> None:
    paths = set(_iter_paths(create_app()))
    assert "/health" in paths
    assert any(path.startswith("/runs") for path in paths)
    assert any(path.startswith("/v1/") for path in paths)
    assert any(path.startswith("/api/device") for path in paths)
