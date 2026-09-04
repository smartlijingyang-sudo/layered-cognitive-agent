"""lca-gateway-routes-runs-sessions plugin — register /runs (8) + /v1/sessions (8)。

PR-7:把 ``/runs/{run_id}/profile`` 与 ``/runs/{run_id}/evidence/{ref}`` 从
``gateway.routes.build_routes`` 迁过来(build_routes 退役);route count
从 14 → 16。
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
async def test_routes_runs_sessions_register_16_routes() -> None:
    """PR-7: /runs(8) + /v1/sessions(8) = 16。

    /runs 子树 8 条:
      /runs, /runs/{run_id}, /runs/{run_id}/live, /runs/{run_id}/doctor,
      /runs/{run_id}/profile, /runs/{run_id}/evidence/{ref:path},
      /runs/{run_id}/cancel, /runs/{run_id}/answer
    """
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(router._exact) == 16


@pytest.mark.asyncio
async def test_routes_runs_sessions_paths_match_migration_baseline() -> None:
    """迁移后路径覆盖迁移前 ``build_routes`` 的 /runs + /v1/sessions 子树。"""
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
    expected_sessions = {
        "/v1/sessions",
        "/v1/sessions/{session_id}/messages",
        "/v1/sessions/{session_id}/snapshot",
        "/v1/sessions/{session_id}/events",
        "/v1/sessions/{session_id}/commands/answer",
        "/v1/sessions/{session_id}/commands/cancel",
        "/v1/sessions/{session_id}/commands/steer",
        "/v1/sessions/{session_id}/commands/inject",
    }
    assert expected_runs.issubset(router._exact.keys())
    assert expected_sessions.issubset(router._exact.keys())


@pytest.mark.asyncio
async def test_routes_runs_sessions_effects_tracked() -> None:
    from lca.plugins.transport.webserver.routes_runs_sessions import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    assert len(ctx._fake_runtime.effects) == 16


def test_routes_runs_sessions_exposes_public_routes_constant() -> None:
    """ADR-0163 决策 5:``ROUTE_SPECS`` 是路径 catalog 的 SSOT,供 build_routes 退役后的测试/诊断直接 import。"""
    from lca.plugins.transport.webserver.routes_runs_sessions import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    paths = {spec.path for spec in ROUTE_SPECS}
    assert "/runs/{run_id}/profile" in paths
    assert "/runs/{run_id}/evidence/{ref:path}" in paths


# ── ADR-0187 §3 D7: session/run assistant_id 绑定 (PR-5) ─────────────


def test_session_create_command_carries_optional_assistant_id() -> None:
    """``SessionCreateCommand`` 新增 ``assistant_id`` 字段（PR-5）。"""
    from lca.contracts.harness.act.command import SessionCreateCommand

    base = SessionCreateCommand(
        idempotency_key="idem-1",
        profile="web-standard",
    )
    assert base.assistant_id is None
    bound = SessionCreateCommand(
        idempotency_key="idem-2",
        profile="web-standard",
        assistant_id="asst_demo",
    )
    assert bound.assistant_id == "asst_demo"


def test_message_send_command_carries_optional_assistant_id() -> None:
    """``MessageSendCommand`` 新增 ``assistant_id`` 字段（PR-5）。"""
    from lca.contracts.harness.act.command import MessageSendCommand

    base = MessageSendCommand(
        idempotency_key="idem-1",
        session_id="ses-1",
        role="user",
        content="hi",
    )
    assert base.assistant_id is None
    bound = MessageSendCommand(
        idempotency_key="idem-2",
        session_id="ses-1",
        role="user",
        content="hi",
        assistant_id="asst_demo",
    )
    assert bound.assistant_id == "asst_demo"


def test_run_request_carries_optional_assistant_id() -> None:
    """``RunRequest`` 新增 ``assistant_id`` 字段（PR-5）。"""
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


def test_normalize_assistant_id_collapses_empty_and_whitespace() -> None:
    """``_normalize_assistant_id`` 归一 None / 空 / 空白 → None。"""
    from lca.plugins.transport.webserver.handlers.session_routes import (
        _normalize_assistant_id,
    )

    assert _normalize_assistant_id(None) is None
    assert _normalize_assistant_id("") is None
    assert _normalize_assistant_id("   ") is None
    assert _normalize_assistant_id("asst_1") == "asst_1"
    assert _normalize_assistant_id("  asst_1  ") == "asst_1"


def test_normalize_assistant_id_rejects_non_string() -> None:
    """``_normalize_assistant_id`` 对非字符串抛 ``ValueError``。"""
    import pytest

    from lca.plugins.transport.webserver.handlers.session_routes import (
        _normalize_assistant_id,
    )

    with pytest.raises(ValueError, match="assistant_id must be a string"):
        _normalize_assistant_id(123)  # type: ignore[arg-type]


def test_session_assistant_id_helper_returns_none_without_persistence() -> None:
    """无 persistence backend 时 helper 返回 None,handler 不抛。"""
    from lca.plugins.transport.webserver.handlers.session_routes import (
        _session_assistant_id,
    )

    class _State:
        pass

    class _App:
        state = _State()

    class _Bare:
        app = _App()

    assert _session_assistant_id(_Bare(), "ses-x") is None
