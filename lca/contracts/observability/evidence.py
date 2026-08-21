"""Evidence contracts —— 受治理的载荷引用与可验证的旁路存储(ADR-0065 §四)。

账本保存发生的事实;证据保存经治理的原始载荷;物化视图是带版本与高水位的
只读投影。本模块定义 L5 / L8 的可执行契约。

关键不变量:
- EvidenceRef 是内容寻址(sha256),同一摘要对应同一份载荷。
- EvidenceStore.get() 读取时必须重新验证摘要,失败返回明确完整性状态
  而非静默降级为 None。
- EvidencePolicy 决定何时内联(账本 data)与何时引用(本 evidence)。
  ``restricted`` 永不内联;``public`` 小于 64KB 默认内联;``best_effort``
  大流可引用。
- EvidenceStore.sweep_orphan() 只清不被 ledger 引用的对象,幂等。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Classification(str, Enum):
    """载荷分类 —— 决定谁能读取与能否外送(ADR-0065 L8 + §四)。

    PUBLIC: 默认外送;SSE / OTel / Langfuse 均可发。
    INTERNAL: 仅 operator;对外 exporter 拒绝。
    RESTRICTED: 仅受授权读取;exporter 拒绝。
    CONFIDENTIAL: 完全受控读取;exporter 拒绝。
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


class RetentionClass(str, Enum):
    """保留期限类 —— 决定 sweep 何时清零(ADR-0065 §四)。"""

    RUN_DEFAULT = "run-default"
    SESSION = "session"
    LONG = "long"
    PERMANENT = "permanent"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """指向 EvidenceStore 一份受治理载荷的不可变引用(ADR-0065 L5)。

    - algorithm + digest:内容寻址;读取端必须验证。
    - media_type:媒体类型(``text/plain`` / ``application/json`` 等)。
    - byte_length:声明的字节数(读取端用做完整性预检)。
    - classification / retention:读取端再次执行策略时使用。
    - locator:backend 私有定位符(fs path / s3 key / 等),不可序列化跨 backend。
    """

    algorithm: str = "sha256"
    digest: str = ""
    media_type: str = "application/octet-stream"
    byte_length: int = 0
    classification: Classification = Classification.INTERNAL
    retention: RetentionClass = RetentionClass.RUN_DEFAULT
    locator: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "digest": self.digest,
            "media_type": self.media_type,
            "byte_length": self.byte_length,
            "classification": self.classification.value,
            "retention": self.retention.value,
            "locator": self.locator,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EvidenceRef:
        return cls(
            algorithm=str(payload.get("algorithm", "sha256")),
            digest=str(payload.get("digest", "")),
            media_type=str(payload.get("media_type", "application/octet-stream")),
            byte_length=int(payload.get("byte_length", 0)),
            classification=Classification(str(payload.get("classification", "internal"))),
            retention=RetentionClass(str(payload.get("retention", "run-default"))),
            locator=str(payload.get("locator", "")),
        )


@dataclass(frozen=True, slots=True)
class EvidenceReceipt:
    """prepare() 成功后返回的不可变收据(ADR-0065 §四)。

    content_sha256 是写入时实际计算的摘要;与 ref.digest 一致才算成功。
    任何不一致都由 backend 抛 IntegrityError。
    """

    ref: EvidenceRef
    prepared_at: float
    prepared_by: str
    content_sha256: str


class EvidenceIntegrityError(RuntimeError):
    """L5:摘要不匹配 / 字节数不一致 / 缺失 —— 显式完整性失败。

    不能静默降级为 None;消费者必须收到明确信号(0065 §四)。
    """


@runtime_checkable
class EvidencePolicy(Protocol):
    """载荷分类 / 保留 / 内联决策(ADR-0065 L5 / L8)。"""

    def classify(
        self,
        payload: bytes,
        *,
        hint: Classification | None = None,
        media_type: str = "application/octet-stream",
    ) -> Classification:
        """根据 payload 内容 + hint 决定分类。"""

    def retention(
        self,
        payload: bytes,
        *,
        hint: RetentionClass | None = None,
    ) -> RetentionClass:
        """根据 payload 大小 + hint 决定保留类。"""

    def should_inline(
        self,
        payload: bytes,
        *,
        classification: Classification,
    ) -> bool:
        """决策:True → 把 payload 塞进账本 data;False → 走 EvidenceRef。

        默认规则:
        - restricted / confidential → False(绝不内联敏感载荷)
        - public / internal 且 size <= 64 KiB → True
        - public / internal 且 size > 64 KiB → False
        """


@runtime_checkable
class EvidenceStore(Protocol):
    """受治理的证据后端契约(ADR-0065 L5)。

    实现要点:
    - prepare() 走"准备 → 验证 → 引用 → 提交"协议,返回不可变 EvidenceReceipt。
    - get() 重新计算摘要并验证;失败抛 EvidenceIntegrityError,不得返回 None
      以掩盖失败。
    - sweep_orphan() 幂等,只清不在 ledger_index 的对象。
    """

    def prepare(
        self,
        payload: bytes,
        *,
        classification: Classification,
        retention: RetentionClass,
        media_type: str = "application/octet-stream",
        prepared_by: str = "",
    ) -> EvidenceReceipt:
        """准备并提交一份证据;返回不可变 receipt。

        Raises:
            EvidenceIntegrityError: 写入失败 / 摘要计算失败
        """

    def get(
        self,
        ref: EvidenceRef,
        *,
        requester: str,
        audience: Classification,
    ) -> bytes:
        """按 ref 读取载荷并验证完整性。

        Raises:
            EvidenceIntegrityError: 摘要不匹配 / 字节数不一致 / 缺失
            PermissionError: requester / audience 不满足 ref.classification 策略
        """

    def contains(self, ref: EvidenceRef) -> bool:
        """纯存在性检查 —— 不读内容,不验证摘要(用于 sweep 之前预筛)。"""

    def sweep_orphan(
        self,
        ledger_index: Mapping[str, set[EvidenceRef]],
    ) -> int:
        """清掉不被 ledger_index 任何 run 引用的对象。返回清掉数量。幂等。"""


__all__ = [
    "Classification",
    "EvidenceIntegrityError",
    "EvidencePolicy",
    "EvidenceReceipt",
    "EvidenceRef",
    "EvidenceStore",
    "RetentionClass",
]
