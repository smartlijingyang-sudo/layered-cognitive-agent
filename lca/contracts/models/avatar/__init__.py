"""Avatar 契约模型（ADR-0269 §2）。

候选池 TTL 恒为 24 小时；AvatarState.active 为 None 表示使用默认头像。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "AVATAR_SIZES",
    "CANDIDATE_TTL",
    "AvatarActiveBundle",
    "AvatarCandidate",
    "AvatarState",
    "AvatarUpdatedEvent",
    "AvatarVariant",
]

CANDIDATE_TTL: timedelta = timedelta(hours=24)
AVATAR_SIZES: tuple[str, ...] = ("original", "small", "medium", "large")


class AvatarVariant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    size: Literal["original", "small", "medium", "large"]
    file_path: str
    url: str
    width: int
    height: int


class AvatarCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    assistant_id: str
    kind: Literal["create", "edit"]
    prompt: str
    variants: tuple[AvatarVariant, ...]
    video_status: Literal["none", "pending", "ready", "failed"] = "none"
    created_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now > self.expires_at


class AvatarActiveBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    variants: tuple[AvatarVariant, ...]
    video_status: Literal["none", "pending", "ready", "failed"] = "none"
    activated_at: datetime


class AvatarState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assistant_id: str
    active: AvatarActiveBundle | None
    candidates: list[AvatarCandidate]
    updated_at: datetime


class AvatarUpdatedEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["avatar_updated", "avatar_video_ready"]
    assistant_id: str
    payload: dict


def utcnow() -> datetime:
    return datetime.now(UTC)
