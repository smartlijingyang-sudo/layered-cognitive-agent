"""ADR-0246 §3.2 — 本机副作用平面领域模型（纯数据，contracts 层）。

CapabilityGrant   副作用许可（许可类，非事实）
EffectReceipt     执行回执（回执类，追加不可变）
LocalExecTarget   执行目标描述（投影摘要）

rules: frozen=True, extra="forbid" (C13)
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class TargetKind(StrEnum):
    """执行目标分类——工具 schema 和 UI 必须据此区分（I-UMS-5）。"""

    SANDBOX = "sandbox"
    USER_MACHINE = "user_machine"
    POOL_WORKER = "pool_worker"


class LocalExecTarget(BaseModel):
    """执行目标描述（投影摘要，不是事实源）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TargetKind
    id: str
    label: str
    capability_summary: Sequence[str]


class CapabilityGrant(BaseModel):
    """短期、窄范围的副作用许可（ADR-0246 §3.2）。

    由控制面签发，Companion 本地再次校验。
    不持久存储；每次 Job 携带，TTL 结束即失效。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    idempotency_key: str
    subject_user_id: str
    subject_machine_id: str
    operation: str
    path_prefixes: Sequence[str]
    command_class: str | None
    command_allowlist: Sequence[str]
    expires_at: int  # Unix timestamp
    approval_id: str | None  # HIL 审批绑定（ADR-0078）
    request_digest: str  # 规范化请求摘要（防 Confused Deputy）


class EffectReceipt(BaseModel):
    """执行回执（不可变，追加进 Session.append，ADR-0246 §3.3）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    idempotency_key: str
    exit_code: int | None
    success: bool
    error_kind: str | None  # device_offline | grant_expired | scope_violation | …
    stdout_digest: str | None
    stderr_digest: str | None


__all__ = [
    "CapabilityGrant",
    "EffectReceipt",
    "LocalExecTarget",
    "TargetKind",
]
