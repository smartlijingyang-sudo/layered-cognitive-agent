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
    assert len(ctx._fake_runtime.effects) == 1


def test_onboarding_route_exposes_public_constant() -> None:
    from lca.plugins.transport.webserver.routes_1.routes_onboarding import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    assert {spec.path for spec in ROUTE_SPECS} == {"/v1/onboarding/presets"}


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
