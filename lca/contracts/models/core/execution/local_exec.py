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


class AccessVerdict(StrEnum):
    """授权判定的三态结果（ADR-0246 §1.1 授权边界）。

    同意边界是另一层：``NEEDS_APPROVAL`` 表示本次请求需要交给
    ADR-0078 的 HIL 状态机,不表示已被拒绝。
    """

    ALLOW = "allow"
    NEEDS_APPROVAL = "needs_approval"
    DENY = "deny"


class AccessReason(StrEnum):
    """判定依据,机器可读,进 receipt 与审批请求。"""

    IN_GRANT = "in_grant"
    OUTSIDE_GRANT = "outside_grant"
    OUTSIDE_WORKING_ROOT = "outside_working_root"
    OPERATION_NOT_GRANTED = "operation_not_granted"
    CREDENTIAL_PATH = "credential_path"
    TEMP_PATH = "temp_path"
    COMMAND_CLASS = "command_class"
    COMMAND_NOT_ALLOWED = "command_not_allowed"
    NOT_A_MACHINE = "not_a_machine"
    JOB_CONTINUATION = "job_continuation"


class AccessDecision(BaseModel):
    """一次授权判定的结果（许可类,非事实;ADR-0246 §1.1）。

    纯值对象。判定方不抛异常、不做 I/O;消费方按 ``verdict`` 分派到
    执行、审批或 ``EffectReceipt(error_kind="scope_violation")``。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: str
    verdict: AccessVerdict
    reason: AccessReason
    path: str = ""
    detail: str = ""


__all__ = [
    "AccessDecision",
    "AccessReason",
    "AccessVerdict",
    "CapabilityGrant",
    "EffectReceipt",
    "LocalExecTarget",
    "TargetKind",
]
