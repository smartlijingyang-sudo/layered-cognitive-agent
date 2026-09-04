"""助理域 EP payload 与发射契约（ADR-0187 §3 D8）。

PR-3 落 ``assistant.created``；PR-8 落 evolve / jobs 四面：
``assistant.skill.evolved.proposed`` / ``assistant.skill.evolved.promoted``
/ ``assistant.job.registered`` / ``assistant.job.fired``。

EP payload 只含**元数据**（id / digest / actor），禁止 SKILL 全文、
procedure 草稿正文进 spine（ADR-0187 §3 D2 末段 + D9）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.observability.assistant_ep_closure import ASSISTANT_REQUIRED_FIELDS

__all__ = [
    "AssistantCreatedEventPayload",
    "AssistantJobFiredEventPayload",
    "AssistantJobRegisteredEventPayload",
    "AssistantSkillEvolvedPromotedEventPayload",
    "AssistantSkillEvolvedProposedEventPayload",
]


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
