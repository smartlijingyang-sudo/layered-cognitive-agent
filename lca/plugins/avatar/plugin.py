"""Avatar 插件装配（ADR-0269 §4，Task 10）。

把 Task 1–9 的组件接成 ``@plugin(id="lca-avatar")`` 单一入口：

- 构造 ``Grok2ApiProvider`` / ``AvatarEventPublisher``，向上下文提供
  ``avatar.service`` / ``avatar.events``；
- 把 ``avatar_service_registry`` 的懒解析器接上：``get(assistant_id)`` 对任意
  助理 id 构造并缓存按助理绑定的 ``AvatarService``（REST/WS/工具共享注册表，
  每个服务持有独立 ``AvatarStore``，spec §5）；
- 调用 ``routes.setup`` 与 ``events.setup`` 挂载 REST 与 WS 路由；
- 启动 ``AvatarCostumeScheduler`` 后台循环消费 ``avatar_schedule`` 创建的
  cron 换装任务（跨所有 assistant home 扫描），并用 ``ProactiveDeliverer``
  发轻量通知（``session.store`` 缺席时 notifier=None，通知 no-op）。

环境配置只经 Profile ``from_env`` 注入（AGENTS.md 插件禁读 ``os.environ``）：
``AVATAR_IMAGE_BASE_URL``（默认 ``http://127.0.0.1:8000/v1``）、
``AVATAR_IMAGE_API_KEY``（必填，缺失 fail-loud）、``AVATAR_IMAGE_MODEL`` /
``AVATAR_IMAGE_EDIT_MODEL``（默认 ``grok-imagine-image-lite``）、
``AVATAR_VIDEO_MODEL``（默认 ``grok-imagine-video``）、
``LCA_ASSISTANTS_ROOT``（默认 ``~/.lca/assistants``）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, SecretStr

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.cron.models import CronJob, CronRun
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.domain.cron.store import CronStore
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.avatar import events, routes
from lca.plugins.avatar.identity import summarize_traits
from lca.plugins.avatar.provider import Grok2ApiProvider
from lca.plugins.avatar.registry import avatar_service_registry
from lca.plugins.avatar.scheduler import AvatarCostumeScheduler
from lca.plugins.avatar.service import AvatarService
from lca.plugins.avatar.store import AvatarStore

__all__ = ["Config", "setup"]

logger = logging.getLogger(__name__)

# 持有后台调度任务引用，避免被 GC（RUF006）；完成即从集合移除。
_scheduler_tasks: set[asyncio.Task[None]] = set()


class Config(BaseModel):
    """Avatar 插件装配配置；全部可选，缺省回落到内置默认值。"""

    model_config = {"extra": "forbid"}

    assistants_root: str | None = None
    api_key: SecretStr | str | None = None
    base_url: str | None = None
    model: str | None = None
    edit_model: str | None = None
    video_model: str | None = None
    tick_seconds: int = 60
    summarizer_llm: Callable[[str], str] | None = None


def _secret_value(value: SecretStr | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


def _resolve_base_dir(config: Config) -> Path:
    return Path(config.assistants_root or "~/.lca/assistants").expanduser()


def _resolve_api_key(config: Config) -> str:
    api_key = _secret_value(config.api_key)
    if not api_key:
        raise RuntimeError(
            "lca-avatar: AVATAR_IMAGE_API_KEY is required. Set AVATAR_IMAGE_API_KEY "
            "in .env (or pass api_key in the avatar plugin config) before boot."
        )
    return api_key


class _AvatarCronStore:
    """跨所有 assistant home 扫描 avatar cron 任务的 CronStore 门面。

    ``avatar_schedule``（ADR-0268）把 CronJob 写在
    ``<assistant_home>/cron/*.json``，直接 ``CronStore(base_dir)`` 会找错位置。
    本门面在 ``list_jobs`` 时遍历 ``base_dir`` 下每个助理目录，并记住
    job_id → assistant_id 映射，供 run 记录读写路由回正确的 home。
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._job_owner: dict[str, str] = {}

    def _assistant_stores(self) -> list[tuple[str, CronStore]]:
        if not self._base_dir.is_dir():
            return []
        return [
            (child.name, CronStore(child))
            for child in sorted(self._base_dir.iterdir())
            if child.is_dir()
        ]

    def cleanup_expired(self, now: datetime) -> int:
        """扫描所有 assistant home 的 avatar 目录，清理过期候选（spec §5）。"""
        removed = 0
        for assistant_id, _ in self._assistant_stores():
            avatar_store = AvatarStore(self._base_dir / assistant_id / "avatar")
            removed += avatar_store.cleanup_expired(now)
        return removed

    def list_jobs(self) -> list[CronJob]:
        self._job_owner.clear()
        jobs: list[CronJob] = []
        for assistant_id, store in self._assistant_stores():
            for job in store.list_jobs():
                self._job_owner[job.id] = assistant_id
                jobs.append(job)
        return jobs

    def _store_for(self, job_id: str) -> CronStore:
        owner = self._job_owner.get(job_id)
        if owner is None:
            raise KeyError(f"unknown avatar cron job: {job_id}")
        return CronStore(self._base_dir / owner)

    def get_run_records(self, job_id: str) -> list[CronRun]:
        return self._store_for(job_id).get_run_records(job_id)

    def append_run(
        self,
        job_id: str,
        *,
        outcome: Literal["completed", "runtime_failure", "timed_out", "superseded"],
        finished_at: Any = None,
        receipts: tuple[Any, ...] = (),
        run_id: str | None = None,
    ) -> str:
        return self._store_for(job_id).append_run(
            job_id,
            outcome=outcome,
            finished_at=finished_at,
            receipts=receipts,
            run_id=run_id,
        )


def _make_notifier(session_store: Any) -> Callable[[str, str], None]:
    """构造定时换装的轻量通知钩子（ProactiveDeliverer + SESSION_APPEND）。

    ``avatar_costume_scheduler._notify(assistant_id, text)`` 只给 assistant_id。
    为避免 ``ProactiveDeliverer`` 在 session 缺失时 ``create`` 伪造会话，
    只在 ``session_store.get(assistant_id)`` 命中已有 session 时才投递；
    没有对应 session 则跳过并记录日志（通知是轻量附加，绝不产生会话）。
    """
    from lca.contracts.atoms.ids.ids import new_id
    from lca.contracts.models.proactive.message import (
        DeliveryTarget,
        DeliveryTargetKind,
        ProactiveMessage,
        ProactiveSource,
    )
    from lca.infrastructure.proactive import ProactiveDeliverer

    deliverer = ProactiveDeliverer(session_store)

    def notifier(assistant_id: str, text: str) -> None:
        if session_store.get(assistant_id) is None:
            logger.info(
                "avatar costume notification skipped: no session for assistant_id=%s",
                assistant_id,
            )
            return
        message = ProactiveMessage(
            id=new_id("avatar_notify"),
            content=text,
            source=ProactiveSource.ROUTINE_CRON,
        )
        target = DeliveryTarget(
            kind=DeliveryTargetKind.SESSION_APPEND,
            session_id=assistant_id,
        )
        deliverer.deliver(message, target)

    return notifier


@plugin(
    id="lca-avatar",
    provides=("avatar.service", "avatar.events"),
    requires=("route_registry",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="filesystem",
    description="Assistant avatar generation system (ADR-0269).",
    test_suite="tests.plugins.avatar.test_plugin",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-avatar.checked", "lca-avatar.served"),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("route_registry",),
        emits=("avatar.routes.registered", "avatar.ws.registered"),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """装配 avatar 插件：服务注册表、REST/WS 路由与定时换装调度器。"""
    base_dir = _resolve_base_dir(config)
    api_key = _resolve_api_key(config)
    base_url = config.base_url or "http://127.0.0.1:8000/v1"
    model = config.model or "grok-imagine-image-lite"
    edit_model = config.edit_model or "grok-imagine-image-lite"
    video_model = config.video_model or "grok-imagine-video"

    provider = Grok2ApiProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        edit_model=edit_model,
        video_model=video_model,
    )
    publisher = events.AvatarEventPublisher()

    def _summarizer(identity: str) -> str:
        # ADR-0269 §3：配置了 ``summarizer_llm`` 则透传 LLM 摘要，否则使用
        # 确定性 fallback（出厂默认）。插件不读 os.environ，只经 Profile 注入。
        return summarize_traits(identity, llm=config.summarizer_llm)

    def _home_resolver(assistant_id: str) -> Path:
        return base_dir / assistant_id

    def _build_service(assistant_id: str) -> AvatarService:
        # spec §5：每个助理独立 ``avatar/`` 目录；服务绑定专属 store，
        # 一个助理永远读不到另一个助理的文件。
        store = AvatarStore(base_dir / assistant_id / "avatar")
        return AvatarService(
            store=store,
            provider=provider,
            summarizer=_summarizer,
            publisher=publisher,
            home_resolver=_home_resolver,
        )

    # 懒解析：REST/WS/工具对任意 assistant_id 都能拿到服务（Task 10 ruling #2）。
    avatar_service_registry.set_resolver(_build_service)

    # ``ctx.provide`` 的默认服务实例（契约要求）。真实访问一律经注册表
    # 懒解析出按 assistant 绑定的服务；该实例仅供兼容面消费。
    service = _build_service("")
    ctx.provide("avatar.service", service)
    ctx.provide("avatar.events", publisher)

    # REST + WS 路由（routes.py / events.py 各自 ctx.require("route_registry")）。
    await routes.setup(ctx, config)
    await events.setup(ctx, config)

    # 定时换装：跨所有 assistant home 扫描 avatar cron 任务；通知经
    # ProactiveDeliverer（session.store 缺席时 notifier=None，不阻塞装配）。
    session_store = ctx.soft_get("session.store")
    scheduler = AvatarCostumeScheduler(
        service_resolver=avatar_service_registry.get,
        cron_store=_AvatarCronStore(base_dir),
        tick_seconds=config.tick_seconds,
        notifier=_make_notifier(session_store) if session_store is not None else None,
    )
    task = asyncio.create_task(scheduler.run_forever())
    _scheduler_tasks.add(task)
    task.add_done_callback(_scheduler_tasks.discard)
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    inner.effect(scheduler.stop, label="avatar:scheduler")
