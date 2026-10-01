"""lca.plugins.transport.webserver.routes_onboarding —— /v1/onboarding/presets (ADR-0252 D7).

验证 RouteSpec 注册与公开常量。
"""

from __future__ import annotations

import pytest

from lca.plugins.transport.webserver.router.router import RouteRegistry


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[object, str]] = []

    def effect(self, dispose: object, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _FakeCtx:
    def __init__(self, router: RouteRegistry) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()

    def require(self, key: str) -> object:
        assert key == "route_registry"
        return self._router

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.mark.asyncio
async def test_onboarding_route_registers() -> None:
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)
    assert "/v1/onboarding/presets" in router._exact
    assert "/v1/onboarding/welcome" in router._exact
    assert "/v1/onboarding/naming/settle" in router._exact
    assert len(ctx._fake_runtime.effects) == 3


def test_onboarding_route_exposes_public_constant() -> None:
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    assert {spec.path for spec in ROUTE_SPECS} == {
        "/v1/onboarding/presets",
        "/v1/onboarding/welcome",
        "/v1/onboarding/naming/settle",
    }


# ── handler 行为（ADR-0252 D7）────────────────────────────────────────


class _FakeResolver:
    def list_departments(self) -> tuple[object, ...]:
        return ((type("Dept", (), {"department_id": "engineering"})()),)

    def list_by_department(self, department_id: str) -> tuple[object, ...]:
        assert department_id == "engineering"
        return (
            (
                type(
                    "Entry",
                    (),
                    {
                        "role_id": "r1",
                        "title": "Arch",
                        "summary": "s",
                        "emoji": "🏛️",
                        "department": "engineering",
                    },
                )()
            ),
        )


class _FakeSkillStore:
    def __init__(self) -> None:
        self.root = type("Root", (), {"__truediv__": lambda self, name: _FakePackage(name)})()

    def list_installed(self) -> tuple[object, ...]:
        return (
            (type("Skill", (), {"skill_id": "sk1", "name": "Skill One", "summary": "does x"})()),
        )


class _FakePackage:
    def __init__(self, name: str) -> None:
        self._name = name

    def __truediv__(self, name: str) -> _FakePackage:
        return _FakePackage(name)

    def is_file(self) -> bool:
        return self._name in {"SKILL.md", "manifest.json"}


@pytest.mark.asyncio
async def test_onboarding_presets_returns_roles_and_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from lca.plugins.transport.webserver.router.router import RouteRegistry
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import (
        setup as plugin,
    )

    monkeypatch.setattr(
        "lca.plugins.transport.webserver.routes_1.routes_onboarding.DiskSkillPackageStore",
        _FakeSkillStore,
    )

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    await plugin.setup(ctx, None)

    app = Starlette()
    router.install(app)
    app.state.role_card_resolver = _FakeResolver()

    client = TestClient(app)
    response = client.get(
        "/v1/onboarding/presets",
        headers={"x-lca-user-id": "alice", "Authorization": "Bearer lca-local"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["roles"] == [
        {"id": "r1", "title": "Arch", "description": "s", "avatar": "🏛️", "category": "engineering"}
    ]
    assert payload["skills"] == [{"id": "sk1", "name": "Skill One", "description": "does x"}]


class _FakeOwnership:
    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.user_mds: dict[str, str] = {}

    def get_onboarding_state(self, user_id: str) -> str:
        return self.states.get(user_id, "pending")

    def set_onboarding_state(self, user_id: str, state: str) -> None:
        self.states[user_id] = state

    def get_user_md(self, user_id: str) -> str | None:
        return self.user_mds.get(user_id)


def test_onboarding_welcome_handler_pending_and_completed() -> None:
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from lca.plugins.transport.webserver.router.router import RouteRegistry
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import (
        onboarding_welcome,
    )

    app = Starlette()
    router = RouteRegistry()
    router.register_http(
        Route("/v1/onboarding/welcome", onboarding_welcome, methods=["GET", "OPTIONS"])
    )
    router.install(app)

    fake_store = _FakeOwnership()
    app.state.assistant_ownership = fake_store

    client = TestClient(app)

    # 1. Pending user -> 2 opening bubbles
    resp_pending = client.get(
        "/v1/onboarding/welcome",
        headers={"x-lca-user-id": "new_user", "Authorization": "Bearer lca-local"},
    )
    assert resp_pending.status_code == 200
    data_pending = resp_pending.json()
    assert data_pending["onboarding_state"] == "pending"
    assert data_pending["step"] == "ask_user_name"
    assert len(data_pending["messages"]) == 2

    # 2. Completed user -> 1 personalized greeting
    fake_store.states["existing_user"] = "completed"
    fake_store.user_mds["existing_user"] = "# USER.md\n- **Name:** 李超\n"

    resp_completed = client.get(
        "/v1/onboarding/welcome?assistant_name=星澜&role_title=架构师",
        headers={"x-lca-user-id": "existing_user", "Authorization": "Bearer lca-local"},
    )
    assert resp_completed.status_code == 200
    data_completed = resp_completed.json()
    assert data_completed["onboarding_state"] == "completed"
    assert data_completed["step"] == "assistant_ready"
    assert len(data_completed["messages"]) == 1
    assert "李超" in data_completed["messages"][0]
    assert "星澜" in data_completed["messages"][0]


@pytest.mark.asyncio
async def test_onboarding_naming_settle_handler() -> None:
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from lca.plugins.transport.webserver.router.router import RouteRegistry
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import (
        onboarding_naming_settle,
    )

    app = Starlette()
    router = RouteRegistry()
    router.register_http(
        Route("/v1/onboarding/naming/settle", onboarding_naming_settle, methods=["POST", "OPTIONS"])
    )
    router.install(app)

    fake_store = _FakeOwnership()
    fake_store.states["user_settle"] = "pending"
    app.state.assistant_ownership = fake_store

    client = TestClient(app)

    resp = client.post(
        "/v1/onboarding/naming/settle",
        json={"assistant_id": "asst_demo", "name": "星澜", "vibe": "敏锐专注"},
        headers={"x-lca-user-id": "user_settle", "Authorization": "Bearer lca-local"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["name"] == "星澜"
    assert data["reaction"] == "🎉"
    assert fake_store.states["user_settle"] == "completed"
