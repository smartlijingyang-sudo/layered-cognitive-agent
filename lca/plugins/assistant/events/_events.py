"""助理域 EP payload 与发射契约（ADR-0187 §3 D8）。

PR-3 落 ``assistant.created``；PR-6 落 ``assistant.skill.installed`` /
``assistant.skill.activated``；PR-8 落 evolve / jobs 四面：
``assistant.skill.evolved.proposed`` / ``assistant.skill.evolved.promoted``
/ ``assistant.job.registered`` / ``assistant.job.fired``。

EP payload 只含**元数据**（id / digest / actor），禁止 SKILL 全文、
procedure 草稿正文进 spine（ADR-0187 §3 D2 末段 + D9）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import structlog

from lca.contracts.observability.closure.assistant_ep_closure import ASSISTANT_REQUIRED_FIELDS

__all__ = [
    "AssistantBootstrapCompletedEventPayload",
    "AssistantCreatedEventPayload",
    "AssistantJobFiredEventPayload",
    "AssistantJobRegisteredEventPayload",
    "AssistantProfileRevisedEventPayload",
    "AssistantSkillActivatedEventPayload",
    "AssistantSkillEvolvedPromotedEventPayload",
    "AssistantSkillEvolvedProposedEventPayload",
    "AssistantSkillInstalledEventPayload",
    "emit_assistant_ep_or_log",
    "emit_fact_event",
]


log = structlog.get_logger(__name__)


def _validate_required_fields(payload: Any, class_name: str) -> None:
    """四件套必含字段守门：``assistant_id`` / ``revision_seq`` /
    ``manifest_digest`` / ``actor``；缺失 / 非法抛 ``ValueError``。"""
    for field_name in ASSISTANT_REQUIRED_FIELDS:
        value = getattr(payload, field_name)
        if field_name == "revision_seq":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{class_name}.{field_name} 必须为非负整数,得到 {value!r}")
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{class_name}.{field_name} 必须为非空字符串")


def _required_dict(payload: Any) -> dict[str, Any]:
    """四件套序列化（所有助理域 EP payload 共享）。"""
    return {
        "assistant_id": payload.assistant_id,
        "revision_seq": payload.revision_seq,
        "manifest_digest": payload.manifest_digest,
        "actor": payload.actor,
    }


@dataclass(frozen=True)
class AssistantCreatedEventPayload:
    """``assistant.created`` EP payload（ADR-0187 §3 D8）。

    必含字段：``assistant_id`` / ``revision_seq`` / ``manifest_digest`` /
    ``actor``（与 ``ASSISTANT_REQUIRED_FIELDS`` 对齐）。构造期由
    :class:`catalog._AssistantCatalogImpl._emit_created` 守门；缺失字段抛 ``ValueError``。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    home_path: str = ""
    template_id: str = ""

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantCreatedEventPayload")

    def to_dict(self) -> dict[str, Any]:
        """按四件套必含字段 + 额外字段序列化；空字段不进 payload。"""
        payload: dict[str, Any] = _required_dict(self)
        if self.home_path:
            payload["home_path"] = self.home_path
        if self.template_id:
            payload["template_id"] = self.template_id
        return payload


@dataclass(frozen=True)
class AssistantBootstrapCompletedEventPayload:
    """``assistant.bootstrap.completed`` EP payload（ADR-0187 §3 D8）。

    引导式创建（``create`` 带 ``seed_user_md``）写 USER.md 后删除
    BOOTSTRAP.md 并发本 EP；四个必含字段与 ``ASSISTANT_REQUIRED_FIELDS``
    对齐，缺失抛 ``ValueError``。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    home_path: str = ""

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantBootstrapCompletedEventPayload")

    def to_dict(self) -> dict[str, Any]:
        """按四件套必含字段 + 额外字段序列化；空字段不进 payload。"""
        payload: dict[str, Any] = _required_dict(self)
        if self.home_path:
            payload["home_path"] = self.home_path
        return payload


@dataclass(frozen=True)
class AssistantProfileRevisedEventPayload:
    """``assistant.profile.revised`` EP payload（ADR-0187 §3 D8 + ADR-0242 D6）。

    配置面任何变更（revise_profile / reimport / skill 删除）经唯一写入口
    落盘后发射；四个必含字段与 ``ASSISTANT_REQUIRED_FIELDS`` 对齐。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    reason: str = ""
    """变更原因（工具语义 / ``"reimport"`` 等）；空 = 未提供。"""
    changes: tuple[str, ...] = ()
    """本次变更涉及的配置面文件名（如 ``("SOUL.md",)``），供审计。"""

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantProfileRevisedEventPayload")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = _required_dict(self)
        if self.reason:
            payload["reason"] = self.reason
        if self.changes:
            payload["changes"] = list(self.changes)
        return payload


@dataclass(frozen=True)
class AssistantSkillEvolvedProposedEventPayload:
    """``assistant.skill.evolved.proposed`` EP payload（ADR-0187 §3 D8 + D9）。

    只含提案元数据：candidate_id / skill_name / draft_digest；
    **禁止**草稿正文（procedure / SKILL 全文）进字段。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    candidate_id: str
    skill_name: str
    draft_digest: str = ""

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantSkillEvolvedProposedEventPayload")
        if not self.candidate_id.strip():
            raise ValueError(
                "AssistantSkillEvolvedProposedEventPayload.candidate_id 必须为非空字符串"
            )
        if not self.skill_name.strip():
            raise ValueError(
                "AssistantSkillEvolvedProposedEventPayload.skill_name 必须为非空字符串"
            )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = _required_dict(self)
        payload["candidate_id"] = self.candidate_id
        payload["skill_name"] = self.skill_name
        if self.draft_digest:
            payload["draft_digest"] = self.draft_digest
        return payload


@dataclass(frozen=True)
class AssistantSkillEvolvedPromotedEventPayload:
    """``assistant.skill.evolved.promoted`` EP payload（ADR-0187 §3 D8 + D9）。

    0067 三闸通过并写入 ``{home}/skills/`` 后发射；只含提升元数据。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    candidate_id: str
    skill_name: str
    approved_by: str
    artifact_digest: str = ""

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantSkillEvolvedPromotedEventPayload")
        for field_name in ("candidate_id", "skill_name", "approved_by"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(
                    f"AssistantSkillEvolvedPromotedEventPayload.{field_name} 必须为非空字符串"
                )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = _required_dict(self)
        payload["candidate_id"] = self.candidate_id
        payload["skill_name"] = self.skill_name
        payload["approved_by"] = self.approved_by
        if self.artifact_digest:
            payload["artifact_digest"] = self.artifact_digest
        return payload


@dataclass(frozen=True)
class AssistantJobRegisteredEventPayload:
    """``assistant.job.registered`` EP payload（ADR-0187 §3 D8 + D10）。"""

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    job_id: str
    work_item_id: str

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantJobRegisteredEventPayload")
        if not self.job_id.strip():
            raise ValueError("AssistantJobRegisteredEventPayload.job_id 必须为非空字符串")
        if not self.work_item_id.strip():
            raise ValueError("AssistantJobRegisteredEventPayload.work_item_id 必须为非空字符串")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = _required_dict(self)
        payload["job_id"] = self.job_id
        payload["work_item_id"] = self.work_item_id
        return payload


@dataclass(frozen=True)
class AssistantJobFiredEventPayload:
    """``assistant.job.fired`` EP payload（ADR-0187 §3 D8 + D10）。

    ``actor`` = Trigger 投递方（Phase 1 恒为 ``"manual"``）。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    job_id: str
    work_item_id: str
    trigger_id: str

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantJobFiredEventPayload")
        for field_name in ("job_id", "work_item_id", "trigger_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"AssistantJobFiredEventPayload.{field_name} 必须为非空字符串")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = _required_dict(self)
        payload["job_id"] = self.job_id
        payload["work_item_id"] = self.work_item_id
        payload["trigger_id"] = self.trigger_id
        return payload


@dataclass(frozen=True)
class AssistantSkillInstalledEventPayload:
    """``assistant.skill.installed`` EP payload（ADR-0187 §3 D8 + D9）。

    发射时机：0067 三闸通过、包落盘 ``{home}/skills/`` 且 manifest
    修订写盘之后（先写盘后发事件;失败不补发）。只记元数据
    （id / digest / actor / state）,**不**携带 SKILL 全文。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    skill_id: str
    skill_digest: str
    artifact_state: str
    source: str = ""
    version: str = ""
    installed_at: str = ""

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantSkillInstalledEventPayload")
        if not self.skill_id or not self.skill_id.strip():
            raise ValueError("AssistantSkillInstalledEventPayload.skill_id 必须为非空字符串")
        if not self.skill_digest or not self.skill_digest.strip():
            raise ValueError("AssistantSkillInstalledEventPayload.skill_digest 必须为非空内容摘要")
        if not self.artifact_state or not self.artifact_state.strip():
            raise ValueError("AssistantSkillInstalledEventPayload.artifact_state 必须为非空状态值")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = _required_dict(self)
        payload["skill_id"] = self.skill_id
        payload["skill_digest"] = self.skill_digest
        payload["artifact_state"] = self.artifact_state
        if self.source:
            payload["source"] = self.source
        if self.version:
            payload["version"] = self.version
        if self.installed_at:
            payload["installed_at"] = self.installed_at
        return payload


@dataclass(frozen=True)
class AssistantSkillActivatedEventPayload:
    """``assistant.skill.activated`` EP payload（ADR-0187 §3 D8）。

    activate 是 run 级事实：不写 Home、不触发 ``revision_seq`` 变化；
    ``revision_seq`` / ``manifest_digest`` 取事件时刻 Home manifest 快照。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    skill_id: str
    activation_id: str
    artifact_state: str = ""
    activated_at: str = ""

    def __post_init__(self) -> None:
        _validate_required_fields(self, "AssistantSkillActivatedEventPayload")
        if not self.skill_id or not self.skill_id.strip():
            raise ValueError("AssistantSkillActivatedEventPayload.skill_id 必须为非空字符串")
        if not self.activation_id or not self.activation_id.strip():
            raise ValueError("AssistantSkillActivatedEventPayload.activation_id 必须为非空字符串")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = _required_dict(self)
        payload["skill_id"] = self.skill_id
        payload["activation_id"] = self.activation_id
        if self.artifact_state:
            payload["artifact_state"] = self.artifact_state
        if self.activated_at:
            payload["activated_at"] = self.activated_at
        return payload


def emit_fact_event(event: str, payload: Mapping[str, Any]) -> Any:
    """Assistant-domain plugin setup() default EP emitter (channel="fact").

    Five setup()s each defined a byte-identical local closure (tool/overlay,
    skill/overlay, evolve, jobs, domain/catalog); converged here with
    identical behavior. The domain_event_publish import stays lazy so plugin
    discovery does not pull in infrastructure at import time.
    """
    from lca.infrastructure.observability.domain_event_publish import (
        publish_structural_event,
    )

    return publish_structural_event(
        execution_point=event,
        channel="fact",
        payload=dict(payload),
        producer=type(None),
    )

def emit_assistant_ep_or_log(
    emit_fn: Callable[[str, Mapping[str, Any]], Any] | None,
    scope: str,
    event: str,
    payload: Mapping[str, Any],
) -> None:
    """Assistant EP 无 emitter fallback 接缝（单元测试路径）。

    九个调用点各自定义了字节级相同的 fallback（domain/catalog 的
    ``_emit_created`` / ``_emit_bootstrap_completed`` /
    ``_emit_profile_revised``、tool/overlay 的 ``_emit_profile_revised``、
    skill/overlay 的 ``_emit_installed`` / ``_emit_profile_revised`` /
    ``_emit_activated``、evolve 的 ``_emit``、jobs 的 ``_emit``）；收敛到此，
    行为完全一致。调用方的 log scope（``assistant.catalog`` /
    ``assistant.tool_overlay`` / ``assistant.skill_overlay`` /
    ``assistant.evolve`` / ``assistant.jobs``）作为参数传入，发射的
    ``<scope>.ep.no_emitter`` 事件字符串不变。
    """
    if emit_fn is None:
        log.info(f"{scope}.ep.no_emitter", ep=event, payload=dict(payload))
        return
    emit_fn(event, dict(payload))
