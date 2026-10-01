"""lca.plugins.transport.webserver.routes_assistants — /v1/assistants (PR-5).

Test the registry surface (7 routes: six catalog/overlay endpoints + two
jobs endpoints sharing one path, PR-8) and the COMPAT 501 envelope used
while the owning capability is absent. The handler bodies must remain
"fail-closed 4xx" (ADR-0187 §3 D7) but never crash the registry boot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from lca.contracts.protocols.assistant.role_resolver import RoleNotFoundError
from lca.plugins.transport.webserver.router.router import RouteRegistry

_STUB_ROLE_CARDS: dict[str, object] = {
    "engineering/architect": {
        "role_id": "engineering/architect",
        "title": "软件架构师",
        "department": "engineering",
        "summary": "系统设计专家",
        "backstory": "# 软件架构师",
        "emoji": "🏛️",
    },
    "engineering/engineering-data-engineer": {
        "role_id": "engineering/engineering-data-engineer",
        "title": "数据工程师",
        "department": "engineering",
        "summary": "数据管线专家",
        "backstory": "# 数据工程师",
        "emoji": "📊",
    },
}


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
    from lca.plugins.transport.webserver.routes_1.routes_assistants import setup as plugin

    router = RouteRegistry()
    ctx = _FakeCtx(router)
    return plugin, router, ctx


@pytest.mark.asyncio
async def test_routes_assistants_register_thirteen_routes() -> None:
    """Thirteen :class:`RouteSpec` entries; ``/v1/assistants`` carries
    both POST (create) and GET (list) via the dispatcher,
    ``/v1/assistants/{assistant_id}/jobs`` carries POST (register) and
    GET (list) via the jobs dispatcher, and standing-files endpoints."""
    plugin, router, ctx = _setup_plugin()
    await plugin.setup(ctx, None)
    assert len(router._exact) == 13


@pytest.mark.asyncio
async def test_routes_assistants_paths_match_advertised_surface() -> None:
    plugin, router, ctx = _setup_plugin()
    await plugin.setup(ctx, None)
    expected = {
        "/v1/assistants",
        "/v1/assistants/import-lobehub",
        "/v1/assistants/{assistant_id}",
        "/v1/assistants/{assistant_id}/profile",
        "/v1/assistants/{assistant_id}:reimport",
        "/v1/assistants/{assistant_id}/skills:install",
        "/v1/assistants/{assistant_id}/bind-agent",
        "/v1/assistants/{assistant_id}/register-lobehub",
        "/v1/assistants/{assistant_id}/retire",
        "/v1/assistants/{assistant_id}/jobs",
        "/v1/assistants/{assistant_id}/jobs/{job_id}:fire",
        "/v1/assistants/{assistant_id}/standing-files",
        "/v1/assistants/{assistant_id}/standing-files/{filename}",
    }
    assert expected.issubset(router._exact.keys())


@pytest.mark.asyncio
async def test_routes_assistants_effects_tracked() -> None:
    plugin, _router, ctx = _setup_plugin()
    await plugin.setup(ctx, None)
    assert len(ctx._fake_runtime.effects) == 13
    labels = {label for _dispose, label in ctx._fake_runtime.effects}
    for path in (
        "/v1/assistants",
        "/v1/assistants/import-lobehub",
        "/v1/assistants/{assistant_id}",
        "/v1/assistants/{assistant_id}/profile",
        "/v1/assistants/{assistant_id}:reimport",
        "/v1/assistants/{assistant_id}/skills:install",
        "/v1/assistants/{assistant_id}/bind-agent",
        "/v1/assistants/{assistant_id}/register-lobehub",
        "/v1/assistants/{assistant_id}/retire",
        "/v1/assistants/{assistant_id}/jobs",
        "/v1/assistants/{assistant_id}/jobs/{job_id}:fire",
        "/v1/assistants/{assistant_id}/standing-files",
        "/v1/assistants/{assistant_id}/standing-files/{filename}",
    ):
        assert f"route:{path}" in labels


def test_routes_assistants_exposes_public_routes_constant() -> None:
    from lca.plugins.transport.webserver.routes_1.routes_assistants import ROUTE_SPECS

    assert isinstance(ROUTE_SPECS, tuple)
    paths = {spec.path for spec in ROUTE_SPECS}
    assert paths == {
        "/v1/assistants",
        "/v1/assistants/import-lobehub",
        "/v1/assistants/{assistant_id}",
        "/v1/assistants/{assistant_id}/profile",
        "/v1/assistants/{assistant_id}:reimport",
        "/v1/assistants/{assistant_id}/skills:install",
        "/v1/assistants/{assistant_id}/bind-agent",
        "/v1/assistants/{assistant_id}/register-lobehub",
        "/v1/assistants/{assistant_id}/retire",
        "/v1/assistants/{assistant_id}/jobs",
        "/v1/assistants/{assistant_id}/jobs/{job_id}:fire",
        "/v1/assistants/{assistant_id}/standing-files",
        "/v1/assistants/{assistant_id}/standing-files/{filename}",
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


def test_install_skill_returns_503_when_overlay_missing() -> None:
    """PR-6: overlay capability 不在场 ⇒ 503 ``skill_overlay_unavailable``。"""
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants/asst_1/skills:install",
        json={"source": {"url": "https://example.com/s.md"}},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "skill_overlay_unavailable"


def test_retire_assistant_returns_501_when_catalog_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.post("/v1/assistants/asst_1/retire", json={"reason": "x"})
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "catalog_unavailable"


# ── jobs routes: 501 COMPAT envelope until assistant.jobs wires ──────


def test_get_assistant_jobs_returns_501_when_jobs_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.get("/v1/assistants/asst_1/jobs")
    assert response.status_code == 501
    body = response.json()
    assert body["error"]["code"] == "jobs_unavailable"
    assert "COMPAT" in body["error"]["marker"]
    assert "delete-when: 2026-12-31" in body["error"]["marker"]


def test_post_assistant_jobs_returns_501_when_jobs_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants/asst_1/jobs",
        json={"job_id": "daily_brief", "schedule": "0 9 * * *", "prompt": "x"},
    )
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "jobs_unavailable"


def test_fire_assistant_job_returns_501_when_jobs_missing() -> None:
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    client = TestClient(app)
    response = client.post("/v1/assistants/asst_1/jobs/daily_brief:fire")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "jobs_unavailable"


# ── PR-6: install handler wired behavior ─────────────────────────────


class _FakeOverlay:
    """Programmable stand-in for ``AssistantSkillOverlay`` on ``app.state``."""

    def __init__(self, *, outcome: str = "ok") -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, Any, str]] = []

    async def install(self, assistant_id: str, source: Any, *, actor: str = "system") -> Any:
        self.calls.append((assistant_id, source, actor))
        if self.outcome == "import_error":
            from lca.contracts.protocols.memory.operational_skills import SkillImportError

            raise SkillImportError("invariant 闸失败: 资源数超过上限")
        if self.outcome == "not_found":
            from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogError

            raise AssistantCatalogError("assistant home 不存在")
        if self.outcome == "digest_mismatch":
            from lca.plugins.domain.assistant.catalog.plugin import AssistantDigestMismatch

            raise AssistantDigestMismatch("digest mismatch")
        from lca.contracts.protocols.assistant.skill_overlay import SkillInstallReceipt

        return SkillInstallReceipt(
            assistant_id=assistant_id,
            skill_id="demo-skill",
            version="1.0.0",
            digest="sha256:abc",
            artifact_state="verified",
            installed_at="2026-09-04T00:00:00Z",
            revision_seq=1,
            manifest_digest="sha256:def",
            actor=actor,
            source=source.reference,
            install_path=f"/home/{assistant_id}/skills/demo-skill",
        )


def _app_with_overlay(overlay: Any) -> TestClient:
    """Materialise routes with ``app.state.assistant_skill_overlay`` set."""
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = _app_with_routes(router)
    app.state.assistant_skill_overlay = overlay
    return TestClient(app)


def test_install_skill_success_returns_receipt() -> None:
    client = _app_with_overlay(_FakeOverlay())
    response = client.post(
        "/v1/assistants/asst_1/skills:install",
        json={"source": {"url": "https://example.com/s.md"}, "actor": "user:demo"},
    )
    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["skill_id"] == "demo-skill"
    assert receipt["artifact_state"] == "verified"
    assert receipt["revision_seq"] == 1
    assert receipt["manifest_digest"] == "sha256:def"
    assert receipt["actor"] == "user:demo"


def test_install_skill_bare_url_string_source_accepted() -> None:
    overlay = _FakeOverlay()
    client = _app_with_overlay(overlay)
    response = client.post(
        "/v1/assistants/asst_1/skills:install",
        json={"source": "https://example.com/s.md"},
    )
    assert response.status_code == 200
    _assistant_id, source, _actor = overlay.calls[0]
    assert source.url == "https://example.com/s.md"


def test_install_skill_rejected_maps_to_422() -> None:
    client = _app_with_overlay(_FakeOverlay(outcome="import_error"))
    response = client.post(
        "/v1/assistants/asst_1/skills:install",
        json={"source": {"url": "https://example.com/s.md"}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "install_rejected"


def test_install_skill_unknown_assistant_maps_to_404() -> None:
    client = _app_with_overlay(_FakeOverlay(outcome="not_found"))
    response = client.post(
        "/v1/assistants/asst_x/skills:install",
        json={"source": {"local_path": "/tmp/pkg"}},  # noqa: S108 - test fixture
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "assistant_not_found"


def test_install_skill_digest_mismatch_maps_to_409() -> None:
    client = _app_with_overlay(_FakeOverlay(outcome="digest_mismatch"))
    response = client.post(
        "/v1/assistants/asst_1/skills:install",
        json={"source": {"url": "https://example.com/s.md"}},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "digest_mismatch"


def test_install_skill_invalid_source_shape_maps_to_400() -> None:
    client = _app_with_overlay(_FakeOverlay())
    response = client.post(
        "/v1/assistants/asst_1/skills:install",
        json={"source": {"url": "ftp://bad", "local_path": "/x"}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_source"


def test_install_skill_missing_source_maps_to_400() -> None:
    client = _app_with_overlay(_FakeOverlay())
    response = client.post("/v1/assistants/asst_1/skills:install", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_source"


def test_install_skill_invalid_json_maps_to_400() -> None:
    client = _app_with_overlay(_FakeOverlay())
    response = client.post(
        "/v1/assistants/asst_1/skills:install",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_json"


# ── Plugin manifest / ADR contract ────────────────────────────────────


def test_routes_assistants_plugin_id_convention() -> None:
    """ADR-0187 §3 D6 plugin module id must align with the dir hierarchy."""
    from lca.plugins.transport.webserver.routes_1.routes_assistants import setup as plugin

    defn = plugin._lca_definition
    assert defn.id == "lca.plugins.transport.webserver.routes_1.routes_assistants"


def test_routes_assistants_plugin_does_not_require_catalog_at_boot() -> None:
    """I-A10: web-standard profile must remain mountable without the catalog.

    The plugin declares only ``route_registry`` as a hard requirement;
    catalog / overlay are looked up dynamically via ``app.state`` so the
    plugin stays mountable on profiles that do not opt into
    ``assistant-runtime``.
    """
    from lca.plugins.transport.webserver.routes_1.routes_assistants import setup as plugin

    defn = plugin._lca_definition
    required = set(defn.required_capability_keys)
    assert required == {"route_registry"}
    assert "assistant.catalog" not in required
    assert "assistant.skill_overlay" not in required


def test_routes_assistants_provides_route_seam() -> None:
    """Routes plugins declare no capability provides.

    与 routes_device / routes_runs_sessions 等同级插件一致：路由插件把
    RouteSpec 注册进 ``route_registry``，不 ``ctx.provide`` capability；
    ``provides`` 声明而不在 setup 兑现会被 boot 审计拒收
    （missing_provide）。
    """
    from lca.plugins.transport.webserver.routes_1.routes_assistants import setup as plugin

    defn = plugin._lca_definition
    provided = set(defn.provided_capability_keys)
    assert provided == set()


# ── Marker / COMPAT hygiene ───────────────────────────────────────────


def test_not_implemented_marker_carries_delete_when() -> None:
    """The COMPAT marker must carry a delete-when condition (AGENTS.md §1)."""
    from lca.plugins.transport.webserver.routes_1.routes_assistants import (
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
    from lca.plugins.transport.webserver.routes_1.routes_assistants import (
        _catalog_from_request,
        _jobs_from_request,
        _skill_overlay_from_request,
    )

    class _Bare:
        pass

    bare = _Bare()
    assert _catalog_from_request(bare) is None  # type: ignore[arg-type]
    assert _skill_overlay_from_request(bare) is None  # type: ignore[arg-type]
    assert _jobs_from_request(bare) is None  # type: ignore[arg-type]


def test_helpers_use_app_state_when_present() -> None:
    """When ``app.state`` carries the catalog, the helper returns it."""
    from lca.plugins.transport.webserver.routes_1.routes_assistants import (
        _catalog_from_request,
        _jobs_from_request,
        _skill_overlay_from_request,
    )

    class _State:
        assistant_catalog = "catalog-handle"
        assistant_skill_overlay = "overlay-handle"
        assistant_jobs = "jobs-handle"

    class _App:
        state = _State()

    class _Bare:
        app = _App()

    assert _catalog_from_request(_Bare()) == "catalog-handle"
    assert _skill_overlay_from_request(_Bare()) == "overlay-handle"
    assert _jobs_from_request(_Bare()) == "jobs-handle"


# ── Sentinel: ensure handlers are imported and callable ───────────────


def test_handlers_are_coroutine_callables() -> None:
    """Sanity: each exported handler is an async coroutine function."""
    import inspect

    from lca.plugins.transport.webserver.routes_1.routes_assistants import (
        create_assistant,
        create_assistant_job,
        fire_assistant_job,
        get_assistant,
        install_assistant_skill,
        list_assistant_jobs,
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
        list_assistant_jobs,
        create_assistant_job,
        fire_assistant_job,
    ):
        assert inspect.iscoroutinefunction(fn), f"{fn.__name__} must be async"


# ── catalog-present behavior（PR-7 wiring：create/list/get 实装）──────


def _app_with_catalog(tmp_path: Any) -> tuple[Starlette, Any]:
    """Materialise routes with a live AssistantCatalog on app.state."""
    from pathlib import Path

    from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl

    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = Starlette()
    router.install(app)
    catalog = AssistantCatalogImpl(root=Path(tmp_path) / "assistants")
    app.state.assistant_catalog = catalog
    return app, catalog


def test_post_assistants_creates_with_catalog(tmp_path: Any) -> None:
    app, _ = _app_with_catalog(tmp_path)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants",
        json={"name": "小研", "description": "深度研究", "template_id": "assistant.research"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["assistant_id"].startswith("asst_")
    assert body["profile"]["name"] == "小研"
    assert body["profile"]["emoji"] == "🔍"
    assert body["template_id"] == "assistant.research"
    # bridge 未装配时 fail-soft：agent_id 为 null，归属保持 pending
    assert body["agent_id"] is None


def test_post_assistants_rejects_missing_name(tmp_path: Any) -> None:
    app, _ = _app_with_catalog(tmp_path)
    client = TestClient(app)
    response = client.post("/v1/assistants", json={"description": "无名"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_post_assistants_rejects_unknown_template(tmp_path: Any) -> None:
    app, _ = _app_with_catalog(tmp_path)
    client = TestClient(app)
    response = client.post("/v1/assistants", json={"name": "x", "template_id": "assistant.nope"})
    assert response.status_code == 400


class _StubRoleResolverForRoutes:
    """Role resolver that only knows one role id (D1 regression)."""

    def resolve(self, role_id: str) -> object:
        if role_id not in _STUB_ROLE_CARDS:
            raise RoleNotFoundError(f"unknown: {role_id}")
        card = _STUB_ROLE_CARDS[role_id]
        return type("RoleCard", (), card)()

    def list_available(self) -> tuple[str, ...]:
        return tuple(sorted(_STUB_ROLE_CARDS))


def _app_with_catalog_and_role_resolver(tmp_path: Any) -> Starlette:
    """Catalog backed by a role resolver for from_role integration tests."""
    from pathlib import Path

    from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl

    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = Starlette()
    router.install(app)
    catalog = AssistantCatalogImpl(
        root=Path(tmp_path) / "assistants",
        role_resolver=_StubRoleResolverForRoutes(),
    )
    app.state.assistant_catalog = catalog
    return app


def test_onboarding_flow_default_soul_reaches_prompt(tmp_path: Any) -> None:
    """登录向导的请求体走到人设提示。

    同一条真实角色卡走两遍。不带开关时 backstory 进 SOUL。
    带上向导的 use_template_soul 后，磁盘、persona 和 BACKSTORY 行都是默认人格。
    角色的 emoji、role_id、goals 仍留下。
    """
    from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
    from lca.infrastructure.tools.assistant.role_card_resolver import FileRoleCardResolver
    from lca.plugins.assistant.persona.persona import persona_from_home
    from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl
    from lca.plugins.prompts.sections import BackstorySection

    role_id = "engineering/engineering-software-architect"
    roles = Path(__file__).resolve().parents[4] / "roles"
    plugin, router, ctx = _setup_plugin()
    _run_plugin_setup(plugin, ctx)
    app = Starlette()
    router.install(app)
    resolver = FileRoleCardResolver(root=roles)
    catalog = AssistantCatalogImpl(
        root=Path(tmp_path) / "assistants",
        role_resolver=resolver,
    )
    app.state.assistant_catalog = catalog
    client = TestClient(app)
    card = resolver.resolve(role_id)
    marker = "限界上下文"
    assert marker in card.backstory

    leaked = client.post(
        "/v1/assistants",
        json={
            "client_id": "flow-backstory",
            "name": "旧路径",
            "description": "对照",
            "from_role": role_id,
            "initial_skills": [],
        },
    )
    assert leaked.status_code == 201
    leaked_soul = (Path(leaked.json()["home_path"]) / "SOUL.md").read_text(encoding="utf-8")
    assert marker in leaked_soul

    created = client.post(
        "/v1/assistants",
        json={
            "client_id": "flow-default-soul",
            "name": "小架",
            "description": "架构顾问",
            "from_role": role_id,
            "initial_skills": [],
            "use_template_soul": True,
        },
    )
    assert created.status_code == 201
    body = created.json()
    home = Path(body["home_path"])
    soul = (home / "SOUL.md").read_text(encoding="utf-8")
    assert "你不是聊天机器人" in soul
    assert "你是 小架" in soul
    assert "架构顾问" in soul
    assert "主要语言：zh-CN" in soul
    assert marker not in soul
    assert "{{ name }}" not in soul
    assert body["profile"]["role_id"] == role_id
    assert body["profile"]["emoji"] == "🏛️"

    goals = (home / "goals.yaml").read_text(encoding="utf-8")
    assert "软件架构师核心职责" in goals

    persona = persona_from_home(str(home))
    assert persona.role == "小架"
    assert persona.goal == "架构顾问"
    assert "你不是聊天机器人" in persona.backstory
    assert marker not in persona.backstory
    profile = RoleProfile(
        role=persona.role,
        goal=persona.goal,
        backstory=persona.backstory,
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
    )
    rendered = BackstorySection().render(role_profile=profile, tools=[])
    assert rendered.text.startswith("BACKSTORY:")
    assert "你不是聊天机器人" in rendered.text
    assert marker not in rendered.text


def test_post_assistants_use_template_soul_keeps_default_persona(tmp_path: Any) -> None:
    """登录向导带 use_template_soul 时，SOUL 是默认模板，角色卡不覆盖。"""
    app = _app_with_catalog_and_role_resolver(tmp_path)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants",
        json={
            "name": "小架",
            "description": "架构顾问",
            "from_role": "engineering/architect",
            "use_template_soul": True,
        },
    )
    assert response.status_code == 201
    home = response.json()["home_path"]
    soul = (Path(home) / "SOUL.md").read_text(encoding="utf-8")
    assert "你不是聊天机器人" in soul
    assert "# 软件架构师" not in soul
    assert response.json()["profile"]["role_id"] == "engineering/architect"
    assert response.json()["profile"]["emoji"] == "🏛️"


def test_post_assistants_rejects_non_bool_use_template_soul(tmp_path: Any) -> None:
    app, _ = _app_with_catalog(tmp_path)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants",
        json={"name": "小架", "use_template_soul": "yes"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_post_assistants_unknown_from_role_returns_400(tmp_path: Any) -> None:
    """D1 regression: unknown ``from_role`` must be 400, not 500."""
    app = _app_with_catalog_and_role_resolver(tmp_path)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants",
        json={"name": "x", "from_role": "no/such-role"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_get_assistants_lists_created(tmp_path: Any) -> None:
    app, catalog = _app_with_catalog(tmp_path)
    from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest

    catalog.create(CreateAssistantRequest(name="列表助理"))
    client = TestClient(app)
    response = client.get("/v1/assistants")
    assert response.status_code == 200
    items = response.json()["assistants"]
    assert len(items) == 1
    assert items[0]["name"] == "列表助理"


def test_get_assistant_by_id_returns_spec_view(tmp_path: Any) -> None:
    app, catalog = _app_with_catalog(tmp_path)
    from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest

    handle = catalog.create(CreateAssistantRequest(name="单个助理", description="职责"))
    client = TestClient(app)
    response = client.get(f"/v1/assistants/{handle.assistant_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["assistant_id"] == handle.assistant_id
    assert body["profile_name"] == "单个助理"
    assert body["bootstrap"]["soul_digest"]


def test_get_assistant_unknown_returns_404(tmp_path: Any) -> None:
    app, _ = _app_with_catalog(tmp_path)
    client = TestClient(app)
    response = client.get("/v1/assistants/asst_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "assistant_not_found"


def test_get_assistant_digest_mismatch_returns_409(tmp_path: Any) -> None:
    app, catalog = _app_with_catalog(tmp_path)
    from pathlib import Path

    from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest

    handle = catalog.create(CreateAssistantRequest(name="篡改目标"))
    soul = Path(handle.home_path) / "SOUL.md"
    soul.write_text(soul.read_text(encoding="utf-8") + "\n# tamper", encoding="utf-8")
    client = TestClient(app)
    response = client.get(f"/v1/assistants/{handle.assistant_id}")
    # auto_heal_on_get 自愈机制：手改文件后 GET 自动 reimport 恢复 200 并更新 revision
    if response.status_code == 200:
        assert response.json()["revision_seq"] >= 1
    else:
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "digest_mismatch"


# ── ADR-0252 bridge 注册：create_assistant 立即投影 LobeHub agent 行 ──


class _FakeOwnership:
    """In-memory AssistantOwnership stand-in for bridge tests."""

    def __init__(self) -> None:
        self.bindings: dict[str, dict[str, str]] = {}

    def ensure_user(
        self, user_id: str, *, username: str | None = None, email: str | None = None
    ) -> None:
        return None

    def bind(self, binding: Any) -> None:
        self.bindings[binding.assistant_id] = {
            "user_id": binding.user_id,
            "client_id": binding.client_id,
            "agent_id": binding.agent_id or "",
            "status": binding.status,
        }

    def owner_of(self, assistant_id: str) -> str | None:
        row = self.bindings.get(assistant_id)
        return row["user_id"] if row else None

    def assistant_id_for_client(self, user_id: str, client_id: str) -> str | None:
        for asst_id, row in self.bindings.items():
            if row["user_id"] == user_id and row["client_id"] == client_id:
                return asst_id
        return None

    def set_agent_id(self, assistant_id: str, agent_id: str) -> None:
        if assistant_id in self.bindings:
            self.bindings[assistant_id]["agent_id"] = agent_id
            self.bindings[assistant_id]["status"] = "active"

    def agent_id_of(self, assistant_id: str) -> str | None:
        row = self.bindings.get(assistant_id)
        return row["agent_id"] or None if row else None


class _FakeBridge:
    """Record calls and return a canned agent id."""

    def __init__(self, *, agent_id: str | None, enabled: bool = True) -> None:
        self.agent_id = agent_id
        self.enabled = enabled
        self.calls: list[dict[str, Any]] = []

    async def register(self, **kwargs: Any) -> str | None:
        self.calls.append(kwargs)
        return self.agent_id


def _app_with_catalog_and_bridge(
    tmp_path: Any, bridge: _FakeBridge, ownership: _FakeOwnership | None = None
) -> tuple[Starlette, _FakeOwnership, _FakeBridge]:
    app, _catalog = _app_with_catalog(tmp_path)
    app.state.assistant_frontend_bridge = bridge
    store = ownership or _FakeOwnership()
    app.state.assistant_ownership = store
    return app, store, bridge


def test_post_assistants_registers_bridge_when_present(tmp_path: Any) -> None:
    bridge = _FakeBridge(agent_id="agt_abc123")
    app, ownership, bridge = _app_with_catalog_and_bridge(tmp_path, bridge)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants",
        json={"name": "桥接助理", "client_id": "onboarding-1"},
        headers={"cookie": "session=abc"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["agent_id"] == "agt_abc123"
    # bridge 收到浏览器会话 Cookie 与幂等 client_id（ADR-0252 D8）
    assert bridge.calls, "bridge.register 未被调用"
    call = bridge.calls[0]
    assert call["cookie"] == "session=abc"
    assert call["client_id"] == "onboarding-1"
    assert call["system_role"], "SOUL.md 应作为 systemRole 传入"
    # 归属回填为 active
    binding = ownership.bindings[body["assistant_id"]]
    assert binding["agent_id"] == "agt_abc123"
    assert binding["status"] == "active"


def test_post_assistants_skip_frontend_bridge_keeps_the_existing_agent(tmp_path: Any) -> None:
    """Binding an existing Lobe row must not register a second agent."""
    bridge = _FakeBridge(agent_id="agt_should_not_appear")
    app, ownership, bridge = _app_with_catalog_and_bridge(tmp_path, bridge)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants",
        json={
            "name": "默认助理",
            "description": "收件箱默认助理",
            "client_id": "lobe-agent:agt_inbox",
            "use_template_soul": True,
            "skip_frontend_bridge": True,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["assistant_id"].startswith("asst_")
    assert body["agent_id"] is None
    assert bridge.calls == []
    binding = ownership.bindings[body["assistant_id"]]
    assert binding["client_id"] == "lobe-agent:agt_inbox"
    assert binding["agent_id"] == ""


def test_post_assistants_duplicate_client_id_is_idempotent(tmp_path: Any) -> None:
    """D2 regression: same ``(user_id, client_id)`` maps to the same assistant."""
    from lca.infrastructure.persistence.user_store import SqliteUserAssistantStore

    app = _app_with_catalog_and_role_resolver(tmp_path)
    store = SqliteUserAssistantStore(path=tmp_path / "lca.sqlite3")
    app.state.assistant_ownership = store
    client = TestClient(app)
    headers = {"x-lca-user-id": "user-dup"}
    first = client.post(
        "/v1/assistants",
        json={
            "name": "幂等助理",
            "client_id": "dup-client-1",
            "from_role": "engineering/architect",
        },
        headers=headers,
    )
    assert first.status_code == 201
    first_id = first.json()["assistant_id"]

    second = client.post(
        "/v1/assistants",
        json={
            "name": "幂等助理-重试",
            "client_id": "dup-client-1",
            "from_role": "engineering/architect",
        },
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["assistant_id"] == first_id
    # 磁盘上只有一个 Home
    homes = list((tmp_path / "assistants").glob("asst_*"))
    assert len(homes) == 1


def test_post_assistants_multiple_client_ids_create_distinct_homes(tmp_path: Any) -> None:
    """Onboarding 多选：每个 ``(client_id, from_role)`` 生成独立 Home + 归属行。

    前端现在对每个选中角色用独立 client_id 调 ``POST /v1/assistants``
    （ADR-0252 D7 多选修复）。每个助理必须落独立目录、SOUL 用角色卡
    backstory，并且每条 client_id 都有归属记录。
    """
    from lca.infrastructure.persistence.user_store import SqliteUserAssistantStore

    app = _app_with_catalog_and_role_resolver(tmp_path)
    store = SqliteUserAssistantStore(path=tmp_path / "lca.sqlite3")
    app.state.assistant_ownership = store
    client = TestClient(app)
    headers = {"x-lca-user-id": "user-multi"}

    payloads = [
        ("onboard-1", "架构师", "engineering/architect", "# 软件架构师"),
        ("onboard-2", "数据工程师", "engineering/engineering-data-engineer", "# 数据工程师"),
    ]
    created = []
    for client_id, name, role_id, backstory_marker in payloads:
        resp = client.post(
            "/v1/assistants",
            json={
                "name": name,
                "client_id": client_id,
                "from_role": role_id,
                "initial_skills": [],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        created.append(body)
        soul = (Path(body["home_path"]) / "SOUL.md").read_text(encoding="utf-8")
        assert backstory_marker in soul  # 角色卡 backstory 进入 SOUL（非默认模板）
        assert body["profile"]["role_id"] == role_id
        assert body["profile"]["emoji"] == ("🏛️" if role_id == "engineering/architect" else "📊")

    # 两个助理是不同 Home，不互相覆盖
    assert created[0]["assistant_id"] != created[1]["assistant_id"]
    assert created[0]["home_path"] != created[1]["home_path"]

    # 归属表有两条独立记录，client_id 与 role_id 正确
    for client_id, _name, _role_id, _marker in payloads:
        asst_id = store.assistant_id_for_client("user-multi", client_id)
        assert asst_id is not None
        assert store.owner_of(asst_id) == "user-multi"

    # 该用户的归属列表包含两个助理，互不覆盖
    assert set(store.assistant_ids_for("user-multi")) == {c["assistant_id"] for c in created}


def test_post_assistants_bridge_failure_keeps_pending(tmp_path: Any) -> None:
    bridge = _FakeBridge(agent_id=None)
    app, ownership, _bridge = _app_with_catalog_and_bridge(tmp_path, bridge)
    client = TestClient(app)
    response = client.post(
        "/v1/assistants",
        json={"name": "桥接失败助理", "client_id": "onboarding-2"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["agent_id"] is None
    binding = ownership.bindings[body["assistant_id"]]
    assert binding["agent_id"] == ""
    assert binding["status"] == "pending"


def test_post_assistants_bridge_disabled_fail_soft(tmp_path: Any) -> None:
    bridge = _FakeBridge(agent_id=None, enabled=False)
    app, ownership, _bridge = _app_with_catalog_and_bridge(tmp_path, bridge)
    client = TestClient(app)
    response = client.post("/v1/assistants", json={"name": "桥禁用助理"})
    assert response.status_code == 201
    assert response.json()["agent_id"] is None
    assert next(iter(ownership.bindings.values()))["status"] == "pending"
