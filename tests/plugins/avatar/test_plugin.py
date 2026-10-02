"""Avatar 插件装配冒烟测试（Task 10）。

覆盖：
- plugin 模块导出 ``setup`` 与 ``Config``；
- registry 懒解析器 fallback（未注册 ``get`` → resolver 构造 + 缓存；注册优先）；
- ``plugin.setup`` 用 stub ctx 装配：``avatar_service_registry.get`` 返回服务、
  REST/WS 路由挂载、scheduler 后台任务可停止；
- ``routes.setup`` / ``events.setup`` 可独立用 stub ctx 调用；
- ``AVATAR_IMAGE_API_KEY`` 缺失时 fail-loud；
- bundle 引用 avatar 两个插件模块（防孤儿回归）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from lca.plugins.avatar.registry import avatar_service_registry
from lca.plugins.avatar.service import AvatarService

REPO = Path(__file__).resolve().parents[3]
ASSISTANT_RUNTIME_BUNDLE = REPO / "bundles" / "assistant-runtime.yaml"


class _FakeRuntime:
    def __init__(self) -> None:
        self.effects: list[tuple[Any, str]] = []

    def effect(self, dispose: Any, *, label: str = "effect") -> None:
        self.effects.append((dispose, label))


class _StubCtx:
    """PluginContext 的最小桩：支持 provide/require/soft_get/inject/_runtime。"""

    def __init__(self, router: Any) -> None:
        self._router = router
        self._fake_runtime = _FakeRuntime()
        self.provided: dict[str, Any] = {}
        self.required: list[str] = []

    def provide(self, key: str, value: Any) -> None:
        self.provided[key] = value

    def require(self, key: str) -> Any:
        self.required.append(key)
        assert key == "route_registry"
        return self._router

    def soft_get(self, key: str) -> Any | None:
        return None

    def inject(self, key: str, default: Any = None) -> Any:
        return default

    def _runtime(self) -> _FakeRuntime:
        return self._fake_runtime


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    avatar_service_registry.clear()
    yield
    avatar_service_registry.clear()


# ── 模块导出 ─────────────────────────────────────────────────


def test_plugin_module_exports_setup() -> None:
    from lca.plugins.avatar import plugin as plugin_module

    # ``setup`` 是 @plugin 装饰后的 Cordis Plugin 载体；``setup.setup`` 是原函数。
    assert callable(plugin_module.setup.setup)
    assert plugin_module.__all__ == ["Config", "setup"]


# ── registry 懒解析器 fallback ────────────────────────────────


def test_registry_resolver_fallback() -> None:
    with pytest.raises(KeyError):
        avatar_service_registry.get("asst_x")

    # resolver 构造 + 缓存：同一 assistant_id 两次 get 返回同一实例。
    avatar_service_registry.set_resolver(lambda aid: object())
    svc1 = avatar_service_registry.get("asst_x")
    svc2 = avatar_service_registry.get("asst_x")
    assert svc1 is svc2

    # 已注册服务优先于 resolver。
    registered = object()
    avatar_service_registry.register("asst_y", registered)
    assert avatar_service_registry.get("asst_y") is registered

    # clear 同时清空 resolver。
    avatar_service_registry.clear()
    with pytest.raises(KeyError):
        avatar_service_registry.get("asst_x")


# ── 插件装配 ─────────────────────────────────────────────────


async def test_plugin_setup_wires_registry_routes_and_scheduler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lca.plugins.avatar import plugin as plugin_module
    from lca.plugins.transport.webserver.router.router import RouteRegistry

    router = RouteRegistry()
    ctx = _StubCtx(router)

    created_tasks: list[asyncio.Task[Any]] = []
    real_create_task = asyncio.create_task

    def _recording_create_task(coro: Any) -> asyncio.Task[Any]:
        task = real_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(plugin_module.asyncio, "create_task", _recording_create_task)

    config = plugin_module.Config(
        assistants_root=str(tmp_path),
        api_key=SecretStr("test-key"),
    )
    await plugin_module.setup.setup(ctx, config)

    # registry 懒解析返回真实 AvatarService，store 指向配置的 assistants_root。
    service = avatar_service_registry.get("asst_test")
    assert isinstance(service, AvatarService)
    assert service.store.base_dir == tmp_path

    # 上下文提供了 avatar.service / avatar.events。
    assert "avatar.service" in ctx.provided
    assert "avatar.events" in ctx.provided

    # REST 路由 + WS 路由挂载（routes.setup / events.setup 已被插件调用）。
    assert "/v1/assistants/{id}/avatar" in router._exact
    assert "/v1/assistants/{id}/avatar/candidates" in router._exact
    assert "/v1/assistants/{id}/avatar/set" in router._exact
    assert "/v1/assistants/{id}/avatar/clear" in router._exact
    assert "/v1/assistants/{id}/avatar/files/{path:path}" in router._exact
    assert "/v1/assistants/{id}/events" in router._upgrades

    # scheduler 后台任务已创建，dispose effect 可停止。
    assert len(created_tasks) == 1
    scheduler_dispose = [
        dispose for dispose, label in ctx._fake_runtime.effects if label == "avatar:scheduler"
    ]
    assert scheduler_dispose
    scheduler_dispose[0]()
    await asyncio.wait_for(created_tasks[0], timeout=1)
    assert created_tasks[0].done()


async def test_plugin_setup_fails_without_api_key(tmp_path: Path) -> None:
    from lca.plugins.avatar import plugin as plugin_module
    from lca.plugins.transport.webserver.router.router import RouteRegistry

    ctx = _StubCtx(RouteRegistry())
    config = plugin_module.Config(assistants_root=str(tmp_path))
    with pytest.raises(RuntimeError, match="AVATAR_IMAGE_API_KEY"):
        await plugin_module.setup.setup(ctx, config)


def test_routes_and_events_setup_accept_stub_ctx() -> None:
    """routes.setup / events.setup 可独立用 stub ctx 挂载路由。"""
    from lca.plugins.avatar import events, routes
    from lca.plugins.transport.webserver.router.router import RouteRegistry

    router = RouteRegistry()
    ctx = _StubCtx(router)
    asyncio.run(routes.setup(ctx, None))
    asyncio.run(events.setup(ctx, None))

    assert "/v1/assistants/{id}/avatar/files/{path:path}" in router._exact
    assert "/v1/assistants/{id}/events" in router._upgrades


# ── bundle 引用（防孤儿回归） ─────────────────────────────────


def test_bundle_references_avatar_plugins() -> None:
    import yaml

    data = yaml.safe_load(ASSISTANT_RUNTIME_BUNDLE.read_text(encoding="utf-8"))
    modules = {entry["$module"] for entry in data["entries"]}
    assert "lca.plugins.avatar.plugin" in modules
    assert "lca.plugins.avatar.tools" in modules
