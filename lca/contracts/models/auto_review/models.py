import hashlib
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AutoReviewMode(StrEnum):
    """Auto-Review 审查运行模式。"""

    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


class AutoReviewAction(StrEnum):
    """Auto-Review 决议动作。"""

    ALLOW = "allow"
    ADAPT = "adapt"
    ESCALATE = "escalate"
    BLOCK = "block"


class AutoReviewVerdict(BaseModel):
    """Auto-Review 审查裁决结果载荷。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: AutoReviewAction
    reason: str
    adapted_command: str | None = None
    action_fingerprint: str | None = None


def compute_action_fingerprint(tool_name: str, arguments: dict) -> str:
    """计算确定性 SHA-256 动作指纹，确保 Escalate 人审同一动作不可变重放。"""
    raw = f"{tool_name}:{sorted(arguments.items())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
