"""Message reaction contracts (Muse-aligned react_to_user_message).

A reaction is a single emoji attached to a message, independent of the
text reply. The frontend renders it as a small badge on the message corner.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageReaction(BaseModel):
    """An emoji reaction on a message."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str = Field(description="被贴 reaction 的消息 ID")
    emoji: str = Field(description="单个 emoji，如 🎉 / 👍")
    actor: Literal["assistant", "user"] = Field(
        default="assistant", description="谁贴的"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="贴上时间（UTC）",
    )

    @field_validator("message_id")
    @classmethod
    def _validate_message_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message_id must be a non-empty string")
        return v

    @field_validator("emoji")
    @classmethod
    def _validate_emoji(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("emoji must be a non-empty string")
        if any(ch.isspace() for ch in v):
            raise ValueError("emoji must not contain whitespace")
        if v.isascii():
            # 纯 ASCII 文本不是 emoji（如 "hello"、":party:"）
            raise ValueError("emoji must be an emoji character, not plain text")
        if len(v) > 16:
            raise ValueError("emoji too long; expected a single emoji")
        return v
