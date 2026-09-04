"""助理域 EP payload 与发射契约（ADR-0187 §3 D8）。

PR-3 范围只发 ``assistant.created`` EP;其余 11 个 EP 在后续 PR 落地,
本模块不为它们定义 payload dataclass,以避免 PR-3 范围被空壳类型稀释。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.observability.assistant_ep_closure import ASSISTANT_REQUIRED_FIELDS

__all__ = ["AssistantCreatedEventPayload"]


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
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            value = getattr(self, field_name)
            if field_name == "revision_seq":
                if not isinstance(value, int) or value < 0:
                    raise ValueError(
                        f"AssistantCreatedEventPayload.{field_name} 必须为非负整数,得到 {value!r}"
                    )
                continue
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"AssistantCreatedEventPayload.{field_name} 必须为非空字符串")

    def to_dict(self) -> dict[str, Any]:
        """按四件套必含字段 + 额外字段序列化；空字段不进 payload。"""
        payload: dict[str, Any] = {
            "assistant_id": self.assistant_id,
            "revision_seq": self.revision_seq,
            "manifest_digest": self.manifest_digest,
            "actor": self.actor,
        }
        if self.home_path:
            payload["home_path"] = self.home_path
        if self.template_id:
            payload["template_id"] = self.template_id
        return payload
