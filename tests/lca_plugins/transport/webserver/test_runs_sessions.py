"""lca-gateway-routes-runs-sessions plugin — register /runs routes."""

from __future__ import annotations

from typing import Any

import pytest

from lca.plugins.transport.webserver.router.router import RouteRegistry
from lca.plugins.transport.webserver.routes_2.routes_runs_sessions import ROUTE_SPECS


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


@pytest.mark.asyncio
async def test_routes_runs_sessions_register_expected_count() -> None:
    from lca.plugins.transport.webserver.routes_2.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(router._exact) == len(ROUTE_SPECS)


@pytest.mark.asyncio
async def test_routes_runs_sessions_paths_match_catalog() -> None:
    from lca.plugins.transport.webserver.routes_2.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    expected_runs = {spec.path for spec in ROUTE_SPECS}
    assert expected_runs.issubset(router._exact.keys())
    assert "/runs/{run_id}/live" not in router._exact
    assert "/v1/runs/{run_id}/ws-token" in router._exact


@pytest.mark.asyncio
async def test_routes_runs_sessions_effects_tracked() -> None:
    from lca.plugins.transport.webserver.routes_2.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == len(ROUTE_SPECS)


def test_routes_runs_sessions_exposes_public_routes_constant() -> None:
    paths = {spec.path for spec in ROUTE_SPECS}
    assert "/runs/{run_id}/profile" in paths
    assert "/runs/{run_id}/evidence/{ref:path}" in paths
    assert "/runs/{run_id}/live" not in paths


def test_run_request_carries_optional_assistant_id() -> None:
    from lca.plugins.transport.webserver.handlers.runs.terminal.port.port import RunRequest

    base = RunRequest(
        profile="web-standard",
        question="",
        user_text="hi",
        mode="solo",
        attachment_ids=(),
        prior_turns=(),
        agent=None,
        device_id="",
        plane="",
        extra_plane="",
        execution_target="",
        options={},
        ctx=None,
    )
    assert base.assistant_id is None
