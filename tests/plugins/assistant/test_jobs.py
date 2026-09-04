"""assistant.jobs plugin tests（ADR-0187 §3 D10 + §7 PR-8）。

覆盖契约：

- register ⇒ 0093 WorkItem（trigger / profile / grant / options）+
  ``assistant.job.registered`` EP
- 缺 ``continuous_control_plane_factory`` ⇒ register / fire 拒收
  （:cls:`JobsCapabilityMissing`，fail-closed，不降级隐式线程）
- fire（``actor="manual"``）⇒ MANUAL Trigger 投递 0093 +
  ``assistant.job.fired`` EP
- disabled JobSpec 不进 0093；重复注册幂等（0093 去重）；未注册拒收
- Plugin Manifest 形状（provides / requires / effects / test_suite）
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.capabilities import ASSISTANT_JOBS
from lca.contracts.harness.tasks.continuous import (
    TriggerKind,
    WorkItem,
    WorkStatus,
)
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_JOB_FIRED,
    ASSISTANT_JOB_REGISTERED,
    ASSISTANT_REQUIRED_FIELDS,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.jobs import (
    JobNotRegistered,
    JobsCapabilityMissing,
    JobSpec,
)
from lca.harness.plugin_api import definition_from_plugin
from lca.harness.plugin_manifest import EffectClass
from lca.plugins.assistant.catalog import AssistantCatalogImpl
from lca.plugins.assistant.jobs import AssistantJobsImpl, setup

_FIXED_NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


# ── 0093 fake（内存 WorkQueue 形状）─────────────────────────────────


class _FakePlane:
    """最小 ContinuousControlPlane：submit 按 work_id/trigger_id 去重。"""

    def __init__(self) -> None:
        self.items: dict[str, WorkItem] = {}

    def submit(self, item: WorkItem) -> WorkItem:
        for existing in self.items.values():
            if existing.work_id == item.work_id or (
                existing.trigger.trigger_id == item.trigger.trigger_id
            ):
                return existing
        self.items[item.work_id] = item
        return item

    def get(self, work_id: str) -> WorkItem | None:
        return self.items.get(work_id)

    def status_of(self, work_id: str) -> WorkStatus | None:
        return WorkStatus.PENDING if work_id in self.items else None


class _FakeFactory:
    """最小 ContinuousControlPlaneFactory：共享同一内存队列。"""

    def __init__(self) -> None:
        self.plane = _FakePlane()

    def create(self) -> _FakePlane:
        return self.plane


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def catalog(tmp_path: Path, emitted: list[tuple[str, dict[str, Any]]]) -> AssistantCatalogImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(root=tmp_path, event_emitter=_record)


@pytest.fixture
def factory() -> _FakeFactory:
    return _FakeFactory()


@pytest.fixture
def jobs(
    catalog: AssistantCatalogImpl,
    factory: _FakeFactory,
    emitted: list[tuple[str, dict[str, Any]]],
) -> AssistantJobsImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantJobsImpl(
        catalog=catalog,
        control_plane_factory=factory,
        session_profile="web-assistant",
        event_emitter=_record,
        clock=lambda: _FIXED_NOW,
    )


@pytest.fixture
def assistant_id(catalog: AssistantCatalogImpl) -> str:
    return catalog.create(CreateAssistantRequest(name="Jobs Demo")).assistant_id


@pytest.fixture
def job_spec() -> JobSpec:
    return JobSpec(
        job_id="daily_brief",
        schedule="0 9 * * 1-5",
        prompt="生成今日优先级简报",
    )


# ── register ─────────────────────────────────────────────────────────


class TestRegister:
    def test_register_returns_registration_with_work_item(
        self, jobs: AssistantJobsImpl, assistant_id: str, job_spec: JobSpec
    ) -> None:
        registration = jobs.register(assistant_id, job_spec)
        assert registration.job_id == "daily_brief"
        assert registration.assistant_id == assistant_id
        assert registration.status == "registered"
        assert registration.work_item_id == f"assistant-job-{assistant_id}-daily_brief"

    def test_register_submits_work_item_into_0093(
        self,
        jobs: AssistantJobsImpl,
        factory: _FakeFactory,
        assistant_id: str,
        job_spec: JobSpec,
    ) -> None:
        jobs.register(assistant_id, job_spec)
        item = factory.plane.get(f"assistant-job-{assistant_id}-daily_brief")
        assert item is not None
        assert item.trigger.kind is TriggerKind.SCHEDULE
        assert item.trigger.subject == f"assistant:{assistant_id}:job:daily_brief"
        assert item.profile == "web-assistant"
        assert item.message == "生成今日优先级简报"
        assert item.options["assistant_id"] == assistant_id
        assert item.options["schedule"] == "0 9 * * 1-5"
        # C5：grant 携带助理 grants.yaml allowlist
        assert "workspace.write" in item.grant
        assert "skill.import" in item.grant

    def test_register_emits_job_registered_ep(
        self,
        jobs: AssistantJobsImpl,
        assistant_id: str,
        job_spec: JobSpec,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        jobs.register(assistant_id, job_spec)
        events = [event for event, _ in emitted]
        assert ASSISTANT_JOB_REGISTERED in events
        payload = dict(emitted[events.index(ASSISTANT_JOB_REGISTERED)][1])
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload
        assert payload["job_id"] == "daily_brief"
        assert payload["work_item_id"] == f"assistant-job-{assistant_id}-daily_brief"
        assert payload["actor"] == "system"

    def test_register_idempotent_via_0093_dedup(
        self,
        jobs: AssistantJobsImpl,
        factory: _FakeFactory,
        assistant_id: str,
        job_spec: JobSpec,
    ) -> None:
        first = jobs.register(assistant_id, job_spec)
        second = jobs.register(assistant_id, job_spec)
        assert first.work_item_id == second.work_item_id
        assert len(factory.plane.items) == 1

    def test_register_disabled_jobs_skips_0093(
        self,
        jobs: AssistantJobsImpl,
        factory: _FakeFactory,
        assistant_id: str,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        spec = JobSpec(job_id="paused_job", schedule="0 9 * * *", prompt="x", enabled=False)
        registration = jobs.register(assistant_id, spec)
        assert registration.status == "disabled"
        assert registration.work_item_id == ""
        assert factory.plane.items == {}
        assert all(event != ASSISTANT_JOB_REGISTERED for event, _ in emitted)

    def test_register_unknown_assistant_fails_closed(
        self, jobs: AssistantJobsImpl, job_spec: JobSpec
    ) -> None:
        from lca.plugins.assistant._home_layout import AssistantCatalogError

        with pytest.raises(AssistantCatalogError):
            jobs.register("asst_missing", job_spec)


class TestRegisterWithoutControlPlane:
    def test_missing_capability_rejects_register(
        self, catalog: AssistantCatalogImpl, assistant_id: str, job_spec: JobSpec
    ) -> None:
        impl = AssistantJobsImpl(catalog=catalog, control_plane_factory=None)
        with pytest.raises(JobsCapabilityMissing, match="continuous_control_plane_factory"):
            impl.register(assistant_id, job_spec)

    def test_missing_capability_rejects_fire(
        self, catalog: AssistantCatalogImpl, assistant_id: str
    ) -> None:
        impl = AssistantJobsImpl(catalog=catalog, control_plane_factory=None)
        with pytest.raises(JobsCapabilityMissing):
            impl.fire(assistant_id, "daily_brief")


# ── fire（Phase 1 人工投递）─────────────────────────────────────────


class TestFire:
    def test_fire_delivers_manual_trigger_into_0093(
        self,
        jobs: AssistantJobsImpl,
        factory: _FakeFactory,
        assistant_id: str,
        job_spec: JobSpec,
    ) -> None:
        jobs.register(assistant_id, job_spec)
        handle = jobs.fire(assistant_id, "daily_brief")
        assert handle.assistant_id == assistant_id
        assert handle.job_id == "daily_brief"
        assert handle.status == WorkStatus.PENDING.value
        item = factory.plane.get(handle.work_id)
        assert item is not None
        assert item.trigger.kind is TriggerKind.MANUAL
        assert item.trigger.payload["actor"] == "manual"
        # 投递的 message 复用注册时的 job prompt（0093 队列恢复）
        assert item.message == "生成今日优先级简报"

    def test_fire_emits_job_fired_ep_with_manual_actor(
        self,
        jobs: AssistantJobsImpl,
        assistant_id: str,
        job_spec: JobSpec,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        jobs.register(assistant_id, job_spec)
        handle = jobs.fire(assistant_id, "daily_brief")
        events = [event for event, _ in emitted]
        assert ASSISTANT_JOB_FIRED in events
        payload = dict(emitted[events.index(ASSISTANT_JOB_FIRED)][1])
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload
        assert payload["actor"] == "manual"
        assert payload["job_id"] == "daily_brief"
        assert payload["work_item_id"] == handle.work_id
        assert payload["trigger_id"] == handle.trigger_id

    def test_fire_each_call_creates_fresh_work_item(
        self,
        jobs: AssistantJobsImpl,
        factory: _FakeFactory,
        assistant_id: str,
        job_spec: JobSpec,
    ) -> None:
        jobs.register(assistant_id, job_spec)
        first = jobs.fire(assistant_id, "daily_brief")
        second = jobs.fire(assistant_id, "daily_brief")
        assert first.work_id != second.work_id
        assert first.trigger_id != second.trigger_id

    def test_fire_unregistered_job_rejected(
        self, jobs: AssistantJobsImpl, assistant_id: str
    ) -> None:
        with pytest.raises(JobNotRegistered):
            jobs.fire(assistant_id, "ghost_job")

    def test_fire_disabled_job_rejected(self, jobs: AssistantJobsImpl, assistant_id: str) -> None:
        spec = JobSpec(job_id="paused_job", schedule="0 9 * * *", prompt="x", enabled=False)
        jobs.register(assistant_id, spec)
        with pytest.raises(JobNotRegistered, match="disabled"):
            jobs.fire(assistant_id, "paused_job")

    def test_fire_recovers_registration_from_0093_queue(
        self,
        catalog: AssistantCatalogImpl,
        factory: _FakeFactory,
        assistant_id: str,
        job_spec: JobSpec,
    ) -> None:
        """跨进程恢复：登记不在本进程,但 0093 队列持久 ⇒ 仍可投递。"""
        first_process = AssistantJobsImpl(
            catalog=catalog, control_plane_factory=factory, clock=lambda: _FIXED_NOW
        )
        first_process.register(assistant_id, job_spec)
        second_process = AssistantJobsImpl(
            catalog=catalog, control_plane_factory=factory, clock=lambda: _FIXED_NOW
        )
        handle = second_process.fire(assistant_id, "daily_brief")
        assert handle.status == WorkStatus.PENDING.value


# ── list_jobs ────────────────────────────────────────────────────────


class TestListJobs:
    def test_list_jobs_empty_initially(self, jobs: AssistantJobsImpl, assistant_id: str) -> None:
        assert jobs.list_jobs(assistant_id) == ()

    def test_list_jobs_returns_sorted_registrations(
        self, jobs: AssistantJobsImpl, assistant_id: str
    ) -> None:
        jobs.register(assistant_id, JobSpec(job_id="b_job", schedule="0 1 * * *", prompt="b"))
        jobs.register(assistant_id, JobSpec(job_id="a_job", schedule="0 2 * * *", prompt="a"))
        registrations = jobs.list_jobs(assistant_id)
        assert [r.job_id for r in registrations] == ["a_job", "b_job"]

    def test_list_jobs_isolated_per_assistant(
        self, jobs: AssistantJobsImpl, catalog: AssistantCatalogImpl, assistant_id: str
    ) -> None:
        jobs.register(assistant_id, JobSpec(job_id="only_a", schedule="0 1 * * *", prompt="x"))
        other_id = catalog.create(CreateAssistantRequest(name="Other")).assistant_id
        assert jobs.list_jobs(other_id) == ()


# ── JobSpec 校验 ─────────────────────────────────────────────────────


class TestJobSpecValidation:
    @pytest.mark.parametrize(
        "kwargs",
        (
            {"job_id": "", "schedule": "0 9 * * *", "prompt": "x"},
            {"job_id": "j", "schedule": "", "prompt": "x"},
            {"job_id": "j", "schedule": "0 9 * * *", "prompt": ""},
        ),
    )
    def test_empty_fields_rejected(self, kwargs: dict[str, str]) -> None:
        with pytest.raises(ValueError):
            JobSpec(**kwargs)  # type: ignore[arg-type]


# ── Plugin Manifest 形状 ────────────────────────────────────────────


class TestPluginManifest:
    def test_definition_id_namespace(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.id == "lca.plugins.assistant.jobs"

    def test_provides_assistant_jobs(self) -> None:
        definition = definition_from_plugin(setup)
        assert ASSISTANT_JOBS.key in definition.provided_capability_keys

    def test_requires_catalog_and_control_plane(self) -> None:
        definition = definition_from_plugin(setup)
        required = set(definition.required_capability_keys)
        assert "assistant.catalog" in required
        assert "continuous_control_plane_factory" in required

    def test_effects_are_none(self) -> None:
        """jobs 自身无副作用面（写队列归 0093）。"""
        definition = definition_from_plugin(setup)
        assert EffectClass.NONE in definition.spec.effects
        assert EffectClass.FILESYSTEM not in definition.spec.effects

    def test_test_suite_path_matches(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.verification.test_suite == "tests/plugins/assistant/test_jobs.py"

    def test_ownership_emits_two_job_eps(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.ownership is not None
        assert set(definition.ownership.emits) == {
            ASSISTANT_JOB_REGISTERED,
            ASSISTANT_JOB_FIRED,
        }
