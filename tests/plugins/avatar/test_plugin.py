"""Avatar 插件装配冒烟测试（Task 10）。

覆盖：
- plugin 模块导出 ``setup`` 与 ``Config``；
- registry 懒解析器 fallback（未注册 ``get`` → resolver 构造 + 缓存；注册优先）；
- ``plugin.setup`` 用 stub ctx 装配：``avatar_service_registry.get`` 返回服务、
  REST/WS 路由挂载、scheduler 后台任务可停止；
- ``routes.setup`` / ``events.setup`` 可独立用 stub ctx 调用；
- ``_AvatarCronStore`` 跨 assistant home 聚合 cron 任务、run 记录路由回拥有者；
- notifier 在 session 缺失时跳过投递，绝不 ``create`` 伪造会话；
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

    # registry 懒解析返回真实 AvatarService，store 指向该助理的 avatar 目录。
    service = avatar_service_registry.get("asst_test")
    assert isinstance(service, AvatarService)
    assert service.store.base_dir == tmp_path / "asst_test" / "avatar"

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


async def test_plugin_setup_wires_llm_summarizer(tmp_path: Path) -> None:
    """配置 ``summarizer_llm`` 后，服务经 ``summarize_traits(identity, llm=...)`` 透传。"""
    from lca.plugins.avatar import plugin as plugin_module
    from lca.plugins.transport.webserver.router.router import RouteRegistry

    ctx = _StubCtx(RouteRegistry())
    config = plugin_module.Config(
        assistants_root=str(tmp_path),
        api_key=SecretStr("test-key"),
        summarizer_llm=lambda identity: "llm-traits",
    )
    await plugin_module.setup.setup(ctx, config)

    service = avatar_service_registry.get("asst_llm")
    assert service.summarizer("任意身份文本") == "llm-traits"


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


# ── _AvatarCronStore 跨 assistant home 扫描 ─────────────────────


def test_avatar_cron_store_aggregates_and_routes_runs(tmp_path: Path) -> None:
    """跨两个 assistant home 聚合 avatar cron 任务，run 记录写回拥有者。"""
    from datetime import UTC, datetime

    from lca.contracts.models.cron.models import (
        CronJob,
        DailySchedule,
        SpaceActionExecution,
    )
    from lca.domain.cron.store import CronStore
    from lca.plugins.avatar.plugin import _AvatarCronStore

    base_dir = tmp_path / "assistants"
    (base_dir / "asst_1").mkdir(parents=True)
    (base_dir / "asst_2").mkdir(parents=True)
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    def _avatar_job(job_id: str, owner: str, body: str) -> CronJob:
        return CronJob(
            id=job_id,
            title="avatar",
            schedule=DailySchedule(hour=12, minute=0),
            timezone="Asia/Shanghai",
            body=body,
            execution=SpaceActionExecution(artifact_id="avatar"),
            report="anomalies_only",
            owner=owner,
            created_chat_id="chat_1",
            anchor_at=now,
        )

    CronStore(base_dir / "asst_1").save_job(_avatar_job("job-1", "asst_1", "雨天装扮"))
    CronStore(base_dir / "asst_2").save_job(_avatar_job("job-2", "asst_2", "晴天装扮"))

    store = _AvatarCronStore(base_dir)
    jobs = store.list_jobs()
    assert {j.id for j in jobs} == {"job-1", "job-2"}
    assert {j.owner for j in jobs} == {"asst_1", "asst_2"}

    # append_run 写入拥有者 home 的 cron/<job_id>/runs/，不落到其他 home。
    rid1 = store.append_run("job-1", outcome="completed", finished_at=now)
    assert (base_dir / "asst_1" / "cron" / "job-1" / "runs" / f"{rid1}.json").is_file()
    assert not (base_dir / "asst_2" / "cron" / "job-1" / "runs").exists()

    rid2 = store.append_run("job-2", outcome="runtime_failure", finished_at=now)
    assert (base_dir / "asst_2" / "cron" / "job-2" / "runs" / f"{rid2}.json").is_file()
    assert not (base_dir / "asst_1" / "cron" / "job-2" / "runs").exists()

    # get_run_records 从拥有者 home 读取。
    records1 = store.get_run_records("job-1")
    assert len(records1) == 1
    assert records1[0].outcome == "completed"
    records2 = store.get_run_records("job-2")
    assert len(records2) == 1
    assert records2[0].outcome == "runtime_failure"


def test_avatar_cron_store_cleanup_expired(tmp_path: Path) -> None:
    """调度器扫除：``_AvatarCronStore.cleanup_expired`` 清掉助理 avatar 过期候选。"""
    from datetime import UTC, datetime, timedelta

    from lca.contracts.models.avatar import AvatarState
    from lca.plugins.avatar.plugin import _AvatarCronStore
    from lca.plugins.avatar.store import AvatarStore

    base_dir = tmp_path / "assistants"
    (base_dir / "asst_1").mkdir(parents=True)
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    avatar_store = AvatarStore(base_dir / "asst_1" / "avatar")
    expired = avatar_store._make_candidate(
        "asst_1", "old", "create", "p", now - timedelta(hours=25)
    )
    avatar_store.save_state(
        AvatarState(assistant_id="asst_1", active=None, candidates=[expired], updated_at=now)
    )

    store = _AvatarCronStore(base_dir)
    removed = store.cleanup_expired(now)
    assert removed == 1
    assert avatar_store.load_state("asst_1").candidates == []


# ── notifier session 守卫 ───────────────────────────────────────


def test_notifier_skips_when_no_session_exists() -> None:
    """session 缺失时 notifier 跳过投递，绝不 create 伪造会话。"""
    from types import SimpleNamespace

    from lca.plugins.avatar.plugin import _make_notifier

    class _FakeSession:
        def __init__(self, session_id: str) -> None:
            self.id = session_id
            self.appended: list[tuple[str, dict[str, Any]]] = []

        def append(self, event_type: str, data: dict[str, Any], **kwargs: Any) -> Any:
            self.appended.append((event_type, data))
            return SimpleNamespace(seq=len(self.appended))

    class _FakeSessionStore:
        def __init__(self) -> None:
            self.sessions: dict[str, _FakeSession] = {}
            self.created: list[str] = []

        def get(self, session_id: str) -> _FakeSession | None:
            return self.sessions.get(session_id)

        def create(self, session_id: str | None = None) -> _FakeSession:
            sid = session_id or ""
            self.created.append(sid)
            session = _FakeSession(sid)
            self.sessions[sid] = session
            return session

    store = _FakeSessionStore()
    notifier = _make_notifier(store)

    # 没有 session → 跳过，不调用 create。
    notifier("asst_ghost", "换装完成")
    assert store.sessions == {}
    assert store.created == []

    # 已有 session → 正常投递，且不新建。
    store.sessions["asst_real"] = _FakeSession("asst_real")
    notifier("asst_real", "换装完成")
    assert store.created == []
    assert len(store.sessions["asst_real"].appended) == 1
    assert store.sessions["asst_real"].appended[0][0] == "surface/assistant_message"


# ── bundle 引用（防孤儿回归） ─────────────────────────────────


def test_bundle_references_avatar_plugins() -> None:
    import yaml

    data = yaml.safe_load(ASSISTANT_RUNTIME_BUNDLE.read_text(encoding="utf-8"))
    modules = {entry["$module"] for entry in data["entries"]}
    assert "lca.plugins.avatar.plugin" in modules
    assert "lca.plugins.avatar.tools" in modules


def test_plugin_config_supports_prompt_expander_llm() -> None:
    from lca.plugins.avatar.plugin import Config

    def mock_llm(req: str) -> str:
        return f"expanded: {req}"

    cfg = Config(prompt_expander_llm=mock_llm)
    assert cfg.prompt_expander_llm is mock_llm
