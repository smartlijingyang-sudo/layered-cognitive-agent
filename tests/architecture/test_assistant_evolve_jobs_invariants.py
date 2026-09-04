"""ADR-0187 §5 / §7 PR-8 架构不变量（I-A8 / I-A12 + EP payload 白名单）。

- I-A8：evolve 提案默认 experiment，非 ACTIVE（gate test）；distill 后
  ``skills/`` 为空；审批提升后才写 ``skills/``。
- I-A12：jobs 必经 ADR-0093 WorkQueue（缺 ``continuous_control_plane_factory``
  拒收）；``lca/plugins/assistant/jobs.py`` 无调度线程 / 定时器（静态扫描）。
- evolve / jobs EP payload 只含元数据（字段白名单）；禁 SKILL 全文进 spine。
- evolve 实现 ``SkillAcquirer``（无平行进化协议；§6 删除条件）。

长期回归锁；delete-when: N/A。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_EVENT_POINTS,
    ASSISTANT_JOB_FIRED,
    ASSISTANT_JOB_REGISTERED,
    ASSISTANT_SKILL_EVOLVED_PROMOTED,
    ASSISTANT_SKILL_EVOLVED_PROPOSED,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest

REPO = Path(__file__).resolve().parents[2]
LCA = REPO / "lca"
JOBS_MODULE = LCA / "plugins" / "assistant" / "jobs.py"
EVOLVE_MODULE = LCA / "plugins" / "assistant" / "evolve.py"

_FIXED_NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)

# I-A12 静态扫描：调度**机制**词表（声明式 ``schedule`` 字段名是数据不是机制，
# 不在禁词表；机制 = 线程 / 定时器 / 调度库）。
_SCHEDULER_MECHANISM_TOKENS: tuple[str, ...] = (
    "threading",
    "asyncio.create_task",
    "apscheduler",
    "import schedule",
    "from schedule",
    "schedule.every",
    "Timer(",
    "croniter",
    "setInterval",
    "create_task(",
)

# evolve EP payload 字段白名单（只允许元数据；禁 SKILL 全文 / 草稿正文）
_EVOLVE_EP_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "assistant_id",
        "revision_seq",
        "manifest_digest",
        "actor",
        "candidate_id",
        "skill_name",
        "draft_digest",
        "approved_by",
        "artifact_digest",
    }
)

# 禁入字段（任一出现 = SKILL 全文 / 正文泄漏进 spine）
_EVOLVE_EP_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {"procedure", "content", "body", "text", "skill_md", "full_text", "draft_md"}
)


def _make_env(tmp_path: Path) -> tuple[Any, Any, list[tuple[str, dict[str, Any]]]]:
    """真实 catalog + 真实 evolve impl + EP 记录器。"""
    from lca.plugins.assistant.catalog import AssistantCatalogImpl
    from lca.plugins.assistant.evolve import AssistantEvolveImpl

    emitted: list[tuple[str, dict[str, Any]]] = []

    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    catalog = AssistantCatalogImpl(root=tmp_path, event_emitter=_record)
    evolve = AssistantEvolveImpl(catalog=catalog, event_emitter=_record, clock=lambda: _FIXED_NOW)
    return catalog, evolve, emitted


# ── I-A8：evolve 提案默认 experiment，非 ACTIVE ─────────────────────


class TestIA8EvolveCandidatesDefaultExperiment:
    """distill 产物一律 experiment；``skills/`` 在审批前保持为空。"""

    def test_distilled_candidate_is_experiment_not_active(self, tmp_path: Path) -> None:
        from lca.contracts.protocols.assistant.evolve import ObservationDigest

        catalog, evolve, _ = _make_env(tmp_path)
        assistant_id = catalog.create(CreateAssistantRequest(name="A8")).assistant_id
        digest = ObservationDigest(
            assistant_id=assistant_id,
            run_ids=("run-1",),
            evidence_refs=("spine:run-1",),
            observed_at="2026-09-04T11:00:00Z",
        )
        candidate = evolve.distill(assistant_id, digest)
        assert candidate.status == "experiment"
        assert candidate.status != "active"
        assert candidate.status != "draft"

    def test_distill_leaves_skills_dir_empty(self, tmp_path: Path) -> None:
        from lca.contracts.protocols.assistant.evolve import ObservationDigest

        catalog, evolve, _ = _make_env(tmp_path)
        assistant_id = catalog.create(CreateAssistantRequest(name="A8")).assistant_id
        digest = ObservationDigest(
            assistant_id=assistant_id,
            run_ids=("run-1",),
            evidence_refs=("spine:run-1",),
            observed_at="2026-09-04T11:00:00Z",
        )
        evolve.distill(assistant_id, digest)
        home = Path(catalog.get(assistant_id).home_path)
        assert list((home / "skills").iterdir()) == []

    def test_pending_card_never_marks_active(self, tmp_path: Path) -> None:
        from lca.contracts.protocols.assistant.evolve import ObservationDigest

        catalog, evolve, _ = _make_env(tmp_path)
        assistant_id = catalog.create(CreateAssistantRequest(name="A8")).assistant_id
        digest = ObservationDigest(
            assistant_id=assistant_id,
            run_ids=("run-1",),
            evidence_refs=("spine:run-1",),
            observed_at="2026-09-04T11:00:00Z",
        )
        candidate = evolve.distill(assistant_id, digest)
        home = Path(catalog.get(assistant_id).home_path)
        card = json.loads(
            (home / ".evolve" / "pending" / f"{candidate.candidate_id}.json").read_text()
        )
        assert card["status"] == "experiment"
        assert card["scope"] == "experiment"


# ── I-A12：jobs 无调度线程（静态扫描）───────────────────────────────


class TestIA12JobsNoSchedulerThreads:
    """``lca/plugins/assistant/jobs.py`` 不得含线程 / 定时器 / 调度库。"""

    def test_jobs_module_free_of_scheduler_mechanisms(self) -> None:
        text = JOBS_MODULE.read_text(encoding="utf-8")
        offenders = [token for token in _SCHEDULER_MECHANISM_TOKENS if token in text]
        assert offenders == [], (
            f"I-A12 violated: jobs.py 含调度机制 {offenders}"
            "（jobs 只做 JobSpec 收集与投递,调度归 0093）"
        )

    def test_evolve_module_free_of_scheduler_mechanisms(self) -> None:
        text = EVOLVE_MODULE.read_text(encoding="utf-8")
        offenders = [token for token in _SCHEDULER_MECHANISM_TOKENS if token in text]
        assert offenders == [], f"I-A12 violated: evolve.py 含调度机制 {offenders}"

    def test_jobs_module_does_not_import_asyncio(self) -> None:
        """jobs 面全同步；任何 asyncio 入口都可能引入常驻循环。"""
        text = JOBS_MODULE.read_text(encoding="utf-8")
        assert "import asyncio" not in text


# ── I-A12：jobs 必经 0093（缺 capability 拒收）─────────────────────


class TestIA12JobsMustGoThrough0093:
    """register / fire 必经 ``continuous_control_plane_factory`` → 0093。"""

    def test_jobs_module_consumes_0093_contract_types(self) -> None:
        text = JOBS_MODULE.read_text(encoding="utf-8")
        assert "from lca.contracts.harness.tasks.continuous import" in text
        assert "Trigger" in text
        assert "WorkItem" in text
        assert "ContinuousControlPlaneFactory" in text

    def test_plugin_manifest_requires_control_plane_factory(self) -> None:
        from lca.harness.plugin_api import definition_from_plugin
        from lca.plugins.assistant.jobs import setup

        definition = definition_from_plugin(setup)
        assert "continuous_control_plane_factory" in definition.required_capability_keys

    def test_missing_capability_rejects_register_and_fire(self, tmp_path: Path) -> None:
        from lca.contracts.protocols.assistant.jobs import (
            JobsCapabilityMissing,
            JobSpec,
        )
        from lca.plugins.assistant.catalog import AssistantCatalogImpl
        from lca.plugins.assistant.jobs import AssistantJobsImpl

        catalog = AssistantCatalogImpl(root=tmp_path)
        assistant_id = catalog.create(CreateAssistantRequest(name="A12")).assistant_id
        impl = AssistantJobsImpl(catalog=catalog, control_plane_factory=None)
        spec = JobSpec(job_id="j", schedule="0 9 * * *", prompt="x")
        with pytest.raises(JobsCapabilityMissing):
            impl.register(assistant_id, spec)
        with pytest.raises(JobsCapabilityMissing):
            impl.fire(assistant_id, "j")


# ── evolve EP payload 白名单（禁 SKILL 全文进 spine）────────────────


class TestEvolveEpPayloadWhitelist:
    """proposed / promoted EP payload 字段 ⊆ 元数据白名单。"""

    def _emit_both(self, tmp_path: Path) -> list[tuple[str, dict[str, Any]]]:
        from lca.contracts.protocols.assistant.evolve import (
            ObservationDigest,
            WriteApproval,
        )

        catalog, evolve, emitted = _make_env(tmp_path)
        assistant_id = catalog.create(CreateAssistantRequest(name="EP")).assistant_id
        digest = ObservationDigest(
            assistant_id=assistant_id,
            run_ids=("run-1",),
            evidence_refs=("spine:run-1",),
            observed_at="2026-09-04T11:00:00Z",
        )
        candidate = evolve.distill(assistant_id, digest)
        evolve.promote(
            assistant_id,
            candidate.candidate_id,
            WriteApproval(
                approved_by="reviewer",
                approved_at="2026-09-04T12:00:00Z",
                reason="accept",
            ),
        )
        return emitted

    def test_payload_keys_within_whitelist(self, tmp_path: Path) -> None:
        emitted = self._emit_both(tmp_path)
        ep_events = {ASSISTANT_SKILL_EVOLVED_PROPOSED, ASSISTANT_SKILL_EVOLVED_PROMOTED}
        payloads = [payload for event, payload in emitted if event in ep_events]
        assert len(payloads) == 2
        for payload in payloads:
            extra = set(payload) - _EVOLVE_EP_ALLOWED_KEYS
            assert extra == set(), f"EP payload 含白名单外字段 {extra}"

    def test_payload_never_carries_skill_full_text(self, tmp_path: Path) -> None:
        emitted = self._emit_both(tmp_path)
        ep_events = {ASSISTANT_SKILL_EVOLVED_PROPOSED, ASSISTANT_SKILL_EVOLVED_PROMOTED}
        for event, payload in emitted:
            if event not in ep_events:
                continue
            leaked = _EVOLVE_EP_FORBIDDEN_KEYS & set(payload)
            assert leaked == set(), f"{event} payload 含正文字段 {leaked}"
            for value in payload.values():
                if isinstance(value, str):
                    assert "## Procedure" not in value, f"{event} payload 含草稿正文"

    def test_job_ep_payloads_within_metadata_scope(self, tmp_path: Path) -> None:
        from lca.contracts.protocols.assistant.jobs import JobSpec
        from lca.plugins.assistant.catalog import AssistantCatalogImpl
        from lca.plugins.assistant.jobs import AssistantJobsImpl

        emitted: list[tuple[str, dict[str, Any]]] = []

        def _record(event: str, payload: Mapping[str, Any]) -> None:
            emitted.append((event, dict(payload)))

        catalog = AssistantCatalogImpl(root=tmp_path, event_emitter=_record)
        assistant_id = catalog.create(CreateAssistantRequest(name="Jobs")).assistant_id

        class _Plane:
            def __init__(self) -> None:
                self.items: dict[str, Any] = {}

            def submit(self, item: Any) -> Any:
                self.items[item.work_id] = item
                return item

            def get(self, work_id: str) -> Any | None:
                return self.items.get(work_id)

            def status_of(self, work_id: str) -> Any | None:
                from lca.contracts.harness.tasks.continuous import WorkStatus

                return WorkStatus.PENDING if work_id in self.items else None

        class _Factory:
            def __init__(self) -> None:
                self.plane = _Plane()

            def create(self) -> _Plane:
                return self.plane

        jobs = AssistantJobsImpl(
            catalog=catalog,
            control_plane_factory=_Factory(),
            event_emitter=_record,
            clock=lambda: _FIXED_NOW,
        )
        jobs.register(assistant_id, JobSpec(job_id="j", schedule="0 9 * * *", prompt="x"))
        jobs.fire(assistant_id, "j")
        allowed = {
            "assistant_id",
            "revision_seq",
            "manifest_digest",
            "actor",
            "job_id",
            "work_item_id",
            "trigger_id",
        }
        for event, payload in emitted:
            if event in {ASSISTANT_JOB_REGISTERED, ASSISTANT_JOB_FIRED}:
                extra = set(payload) - allowed
                assert extra == set(), f"{event} payload 含白名单外字段 {extra}"


# ── SkillAcquirer 复用（无平行进化协议）─────────────────────────────


class TestEvolveImplementsSkillAcquirer:
    """``assistant.evolve`` 实现全局 ``SkillAcquirer`` 缝（§6 删除条件）。"""

    def test_impl_satisfies_skill_acquirer_protocol(self, tmp_path: Path) -> None:
        from lca.contracts.protocols.think.learning import SkillAcquirer

        _, evolve, _ = _make_env(tmp_path)
        assert isinstance(evolve, SkillAcquirer)

    def test_impl_is_not_global_auto_acquire_service(self, tmp_path: Path) -> None:
        """同一 Protocol、独立实现；两者不得是同一个类。"""
        from lca.plugins.assistant.evolve import AssistantEvolveImpl
        from lca.plugins.skill.auto_acquire import AutoAcquireSkillService

        assert AssistantEvolveImpl is not AutoAcquireSkillService

    def test_capability_key_distinct_from_global_seam(self) -> None:
        from lca.contracts.capabilities import ASSISTANT_EVOLVE, LEARNING_SKILL_ACQUIRER

        assert ASSISTANT_EVOLVE.key != LEARNING_SKILL_ACQUIRER.key
        assert ASSISTANT_EVOLVE.key == "assistant.evolve"

    def test_evolve_ownership_emits_subset_of_closure(self) -> None:
        from lca.harness.plugin_api import definition_from_plugin
        from lca.plugins.assistant.evolve import setup

        definition = definition_from_plugin(setup)
        assert definition.ownership is not None
        assert set(definition.ownership.emits) <= set(ASSISTANT_EVENT_POINTS)

    def test_jobs_ownership_emits_subset_of_closure(self) -> None:
        from lca.harness.plugin_api import definition_from_plugin
        from lca.plugins.assistant.jobs import setup

        definition = definition_from_plugin(setup)
        assert definition.ownership is not None
        assert set(definition.ownership.emits) <= set(ASSISTANT_EVENT_POINTS)
