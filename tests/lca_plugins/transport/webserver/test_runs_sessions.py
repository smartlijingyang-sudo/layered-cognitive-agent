"""lca-gateway-routes-runs-sessions plugin — register /runs (8)。

``/v1/sessions`` 命令面已随旧 Session Spine 退役（命令入口归 runs 平面）。
"""

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

    def require(self, key: str) -> Any:
        assert key == "route_registry"
        return self._router

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.mark.asyncio
async def test_routes_runs_sessions_register_8_routes() -> None:
    """/runs 子树 8 条:
    /runs, /runs/{run_id}, /runs/{run_id}/live, /runs/{run_id}/doctor,
    /runs/{run_id}/profile, /runs/{run_id}/evidence/{ref:path},
    /runs/{run_id}/cancel, /runs/{run_id}/answer
    """
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(router._exact) == 8


@pytest.mark.asyncio
async def test_routes_runs_sessions_paths_match_migration_baseline() -> None:
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    expected_runs = {
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/live",
        "/runs/{run_id}/doctor",
        "/runs/{run_id}/profile",
        "/runs/{run_id}/evidence/{ref:path}",
        "/runs/{run_id}/cancel",
        "/runs/{run_id}/answer",
    }
    assert expected_runs.issubset(router._exact.keys())


@pytest.mark.asyncio
async def test_routes_runs_sessions_effects_tracked() -> None:
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 8


def test_routes_runs_sessions_exposes_public_routes_constant() -> None:
    """``ROUTE_SPECS`` 是路径 catalog 的 SSOT,供测试/诊断直接 import。"""
    from lca.plugins.transport.webserver.routes_runs_sessions import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    paths = {spec.path for spec in ROUTE_SPECS}
    assert "/runs/{run_id}/profile" in paths
    assert "/runs/{run_id}/evidence/{ref:path}" in paths


def test_run_request_carries_optional_assistant_id() -> None:
    """``RunRequest`` 携带可选 ``assistant_id`` 字段。"""
    from lca.plugins.transport.webserver.handlers.runs.terminal.port import RunRequest

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
