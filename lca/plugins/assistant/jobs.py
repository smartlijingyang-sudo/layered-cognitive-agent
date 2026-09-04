"""assistant.jobs plugin —— ADR-0187 §3 D10 + §7 PR-8。

Job = ADR-0093 持续执行控制面之上的声明式配置（contribution=collect）：
本插件只做 JobSpec 收集与 ``actor="manual"`` 投递，调度 / lease / 去重 /
重试 / dead-letter 全部复用 0093 WorkQueue（``continuous_control_plane_factory``
capability → ``ContinuousControlPlane.submit``）。

**无**线程 / 定时器 / 调度循环（I-A12）；timer / webhook 投递源 =
ADR-0187.1（0093 的 Trigger 来源扩展，不是独立调度器）。

失败语义：

- profile 缺 ``continuous_control_plane_factory`` ⇒ register / fire 抛
  :cls:`JobsCapabilityMissing`（fail-closed，不降级隐式线程）；
- 助理缺失 / digest 不一致 ⇒ catalog.get 抛错透传（I-A3 fail-closed）；
- fire 未注册 job ⇒ :cls:`JobNotRegistered`。

Phase 1 限制：``list_jobs`` 返回本进程 ``register`` 过的登记；跨进程重启
后 ``fire`` 仍可按确定性 work_id 从 0093 队列恢复投递。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import (
    ASSISTANT_CATALOG,
    ASSISTANT_JOBS,
    CONTINUOUS_CONTROL_PLANE_FACTORY,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.harness.tasks.continuous import (
    ContinuousControlPlaneFactory,
    Trigger,
    TriggerKind,
    WorkItem,
    WorkStatus,
)
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_JOB_FIRED,
    ASSISTANT_JOB_REGISTERED,
)
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.assistant.jobs import (
    AssistantJobs,
    JobNotRegistered,
    JobRegistration,
    JobsCapabilityMissing,
    JobSpec,
    WorkItemHandle,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.assistant._events import (
    AssistantJobFiredEventPayload,
    AssistantJobRegisteredEventPayload,
)
from lca.plugins.assistant._home_layout import load_manifest

log = structlog.get_logger(__name__)


# ── Plugin 配置 ───────────────────────────────────────────────────────


class Config(BaseModel):
    """jobs plugin 配置：job WorkItem 打开的新 Session 用哪个 runtime profile。"""

    model_config = ConfigDict(extra="forbid")

    session_profile: str = Field(default="web-assistant", min_length=1)
    """job 触发的新 Session 的 runtime profile（0093 WorkItem.profile）。"""


# ── 实现 ─────────────────────────────────────────────────────────────


class _AssistantJobsImpl(AssistantJobs):
    """jobs 内部实现；通过 plugin ``setup`` 注入 catalog 与 0093 factory。

    单一职责：JobSpec → 0093 WorkItem 的收集 / 投递 / 登记。本类不持有
    线程、定时器或轮询循环；投递后的 lease / 重试归 0093。
    """

    def __init__(
        self,
        *,
        catalog: AssistantCatalog,
        control_plane_factory: ContinuousControlPlaneFactory | None,
        session_profile: str = "web-assistant",
        event_emitter: Callable[[str, Mapping[str, Any]], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._factory = control_plane_factory
        self._session_profile = session_profile
        self._emit_fn = event_emitter
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._registrations: dict[tuple[str, str], JobRegistration] = {}

    # ── AssistantJobs 面 ─────────────────────────────────────────────

    def register(self, assistant_id: str, job_spec: JobSpec) -> JobRegistration:
        """收 JobSpec → 注册 0093 WorkItem；发 ``assistant.job.registered`` EP。

        0093 ``submit`` 按 ``work_id`` / ``trigger_id`` 去重：同一 job 重复
        注册幂等返回既有 work item。``enabled=False`` 的 JobSpec 不进 0093。
        """
        plane = self._require_factory("register").create()
        spec = self._catalog.get(assistant_id)  # digest 校验（I-A3 fail-closed）
        if not job_spec.enabled:
            registration = JobRegistration(
                job_id=job_spec.job_id,
                assistant_id=assistant_id,
                work_item_id="",
                status="disabled",
            )
            self._registrations[(assistant_id, job_spec.job_id)] = registration
            return registration

        work_id = _registration_work_id(assistant_id, job_spec.job_id)
        trigger = Trigger(
            trigger_id=work_id,
            kind=TriggerKind.SCHEDULE,
            occurred_at=self._clock(),
            subject=f"assistant:{assistant_id}:job:{job_spec.job_id}",
            payload={
                "assistant_id": assistant_id,
                "job_id": job_spec.job_id,
                "schedule": job_spec.schedule,
            },
        )
        item = self._build_work_item(
            work_id=work_id,
            trigger=trigger,
            assistant_id=assistant_id,
            job_spec=job_spec,
            home=Path(spec.home_path),
        )
        submitted = plane.submit(item)
        registration = JobRegistration(
            job_id=job_spec.job_id,
            assistant_id=assistant_id,
            work_item_id=submitted.work_id,
            status="registered",
        )
        self._registrations[(assistant_id, job_spec.job_id)] = registration

        manifest_digest = str(load_manifest(Path(spec.home_path), assistant_id)["manifest_digest"])
        self._emit(
            ASSISTANT_JOB_REGISTERED,
            AssistantJobRegisteredEventPayload(
                assistant_id=assistant_id,
                revision_seq=spec.revision_seq,
                manifest_digest=manifest_digest,
                actor="system",
                job_id=job_spec.job_id,
                work_item_id=submitted.work_id,
            ).to_dict(),
        )
        return registration

    def list_jobs(self, assistant_id: str) -> tuple[JobRegistration, ...]:
        """列本进程已登记 job（按 job_id 排序）。"""
        self._catalog.get(assistant_id)  # 未知助理 / digest 不一致 ⇒ fail-closed
        return tuple(
            sorted(
                (
                    registration
                    for (registered_assistant, _), registration in self._registrations.items()
                    if registered_assistant == assistant_id
                ),
                key=lambda registration: registration.job_id,
            )
        )

    def fire(self, assistant_id: str, job_id: str) -> WorkItemHandle:
        """人工投递一次 ``actor="manual"`` Trigger 进 0093；发 fired EP。

        投递的 WorkItem message 复用注册时登记的 job prompt（从 0093 队列
        按确定性 work_id 恢复，跨进程重启不丢）。
        """
        plane = self._require_factory("fire").create()
        spec = self._catalog.get(assistant_id)
        registration = self._registrations.get((assistant_id, job_id))
        registered_item = plane.get(_registration_work_id(assistant_id, job_id))
        if registration is None and registered_item is None:
            raise JobNotRegistered(
                f"assistant={assistant_id!r} job={job_id!r} 未注册,先走 register"
            )
        if registration is not None and registration.status == "disabled":
            raise JobNotRegistered(
                f"assistant={assistant_id!r} job={job_id!r} 处于 disabled,拒收投递"
            )

        trigger = Trigger(
            trigger_id=f"manual-fire-{uuid.uuid4().hex[:12]}",
            kind=TriggerKind.MANUAL,
            occurred_at=self._clock(),
            subject=f"assistant:{assistant_id}:job:{job_id}",
            payload={"assistant_id": assistant_id, "job_id": job_id, "actor": "manual"},
        )
        options: dict[str, Any] = {
            "assistant_id": assistant_id,
            "job_id": job_id,
            "kind": "assistant.job.fire",
        }
        if registered_item is not None:
            registered_schedule = registered_item.options.get("schedule")
            if isinstance(registered_schedule, str):
                options["schedule"] = registered_schedule
        item = WorkItem(
            work_id=f"assistant-fire-{assistant_id}-{job_id}-{trigger.trigger_id}",
            trigger=trigger,
            profile=self._session_profile,
            message=registered_item.message if registered_item is not None else "",
            options=options,
            grant=_assistant_grants(Path(spec.home_path)),
        )
        submitted = plane.submit(item)
        status = plane.status_of(submitted.work_id) or WorkStatus.PENDING

        manifest_digest = str(load_manifest(Path(spec.home_path), assistant_id)["manifest_digest"])
        self._emit(
            ASSISTANT_JOB_FIRED,
            AssistantJobFiredEventPayload(
                assistant_id=assistant_id,
                revision_seq=spec.revision_seq,
                manifest_digest=manifest_digest,
                actor="manual",
                job_id=job_id,
                work_item_id=submitted.work_id,
                trigger_id=trigger.trigger_id,
            ).to_dict(),
        )
        return WorkItemHandle(
            work_id=submitted.work_id,
            assistant_id=assistant_id,
            job_id=job_id,
            trigger_id=trigger.trigger_id,
            status=status.value,
        )

    # ── 内部 ─────────────────────────────────────────────────────────

    def _require_factory(self, op: str) -> ContinuousControlPlaneFactory:
        """factory 缺失 ⇒ :cls:`JobsCapabilityMissing`（fail-closed）。"""
        if self._factory is None:
            raise JobsCapabilityMissing(
                f"assistant.jobs.{op} 拒收:profile 缺 {CONTINUOUS_CONTROL_PLANE_FACTORY.key}"
                " capability(ADR-0187 §3 D10,不降级隐式线程)"
            )
        return self._factory

    def _build_work_item(
        self,
        *,
        work_id: str,
        trigger: Trigger,
        assistant_id: str,
        job_spec: JobSpec,
        home: Path,
    ) -> WorkItem:
        """JobSpec → 0093 WorkItem；grant 携带助理 grants.yaml 的 allowlist（C5）。"""
        return WorkItem(
            work_id=work_id,
            trigger=trigger,
            profile=self._session_profile,
            message=job_spec.prompt,
            options={
                "assistant_id": assistant_id,
                "job_id": job_spec.job_id,
                "schedule": job_spec.schedule,
                "kind": "assistant.job",
            },
            grant=_assistant_grants(home),
        )

    def _emit(self, event: str, payload: Mapping[str, Any]) -> None:
        """发 EP；无 emitter 时仅 log（单元测试路径）。"""
        if self._emit_fn is None:
            log.info("assistant.jobs.ep.no_emitter", ep=event, payload=dict(payload))
            return
        self._emit_fn(event, dict(payload))


# ── helpers ──────────────────────────────────────────────────────────


def _registration_work_id(assistant_id: str, job_id: str) -> str:
    """注册 WorkItem 的确定性 id（0093 按本 id 去重 + 跨进程恢复）。"""
    return f"assistant-job-{assistant_id}-{job_id}"


def _assistant_grants(home: Path) -> tuple[str, ...]:
    """读 ``grants.yaml`` 的 capability allowlist；缺失 / 非法 ⇒ 空元组。

    空 = 最窄 grant（fail-closed 收窄）；job 的 capability ⊆ 助理 grant（C5）。
    """
    path = home / "grants.yaml"
    if not path.is_file():
        return ()
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return ()
    if not isinstance(parsed, dict):
        return ()
    grants = parsed.get("grants")
    if not isinstance(grants, list):
        return ()
    return tuple(str(grant) for grant in grants if isinstance(grant, str) and grant.strip())


# ── Plugin manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.jobs",
    provides=(ASSISTANT_JOBS.key,),
    requires=(ASSISTANT_CATALOG.key, CONTINUOUS_CONTROL_PLANE_FACTORY.key),
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.NONE,),
    description=(
        "JobSpec 收集 → ADR-0093 WorkQueue 注册 / 人工投递;无线程、定时器或"
        "调度循环;缺 continuous_control_plane_factory ⇒ 拒收(ADR-0187 §3 D10)。"
    ),
    test_suite="tests/plugins/assistant/test_jobs.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("assistant.jobs.register", "assistant.jobs.fire")),
        observability=EvidenceContract(descriptors=(ASSISTANT_JOB_REGISTERED, ASSISTANT_JOB_FIRED)),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key, CONTINUOUS_CONTROL_PLANE_FACTORY.key),
        emits=(ASSISTANT_JOB_REGISTERED, ASSISTANT_JOB_FIRED),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """assistant.jobs plugin boot：取 catalog + 0093 factory,暴露 ``assistant.jobs``。

    失败语义：``continuous_control_plane_factory`` 缺失 ⇒ ``ctx.require``
    抛 MissingCapabilityError,plugin boot 失败(fail-closed;ADR-0187 §3 D10
    禁止降级为隐式线程)。
    """
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"assistant.jobs requires {ASSISTANT_CATALOG.key} 为 AssistantCatalog,"
            f"得到 {type(catalog).__name__}"
        )
    factory = ctx.require(CONTINUOUS_CONTROL_PLANE_FACTORY.key)
    if not isinstance(factory, ContinuousControlPlaneFactory):
        raise TypeError(
            f"assistant.jobs requires {CONTINUOUS_CONTROL_PLANE_FACTORY.key} 为"
            f" ContinuousControlPlaneFactory,得到 {type(factory).__name__}"
        )

    def _emit(event: str, payload: Mapping[str, Any]) -> Any:
        return ctx.emit(event, dict(payload))

    impl = _AssistantJobsImpl(
        catalog=catalog,
        control_plane_factory=factory,
        session_profile=config.session_profile,
        event_emitter=_emit,
    )
    ctx.provide(ASSISTANT_JOBS.key, impl)


# 用于测试在不接 ctx 时直接构造
AssistantJobsImpl = _AssistantJobsImpl

__all__ = [
    "AssistantJobsImpl",
    "Config",
    "setup",
]
