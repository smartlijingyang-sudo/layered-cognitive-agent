"""第5.5节：记忆记录与时态关系契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind


class MemoryTrust(str, Enum):
    """模型消费记忆时必须遵守的可信度分级。"""

    TRUSTED = "trusted"
    UNTRUSTED_HISTORY = "untrusted_history"


class MemoryRelationKind(str, Enum):
    """时态记忆图中允许的事实关系。"""

    EXTENDS = "extends"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"


@dataclass
class MemoryRecord:
    """多级记忆记录，兼容时态事实与来源治理。

    原有的四层记忆字段保留不变。时态字段均以 UTC epoch milliseconds
    表示；``None`` 代表由具体存储实现写入观察时刻或事实仍然有效。
    ``trust`` 决定渲染到模型时是否必须进入不可信历史证据通道。
    """

    record_id: str
    content: str
    memory_type: MemoryLayer
    importance: float
    recency_score: float | None = None
    embedding: list[float] | None = None
    source_trace_id: str | None = None
    ttl: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    kind: MemoryRecordKind = MemoryRecordKind.GENERIC
    provenance: str = ""
    confidence: float | None = None
    deleted: bool = False
    scope_id: str = ""
    created_at_ms: int | None = None
    observed_at_ms: int | None = None
    valid_from_ms: int | None = None
    valid_until_ms: int | None = None
    retired_at_ms: int | None = None
    revision_of: str | None = None
    trust: MemoryTrust = MemoryTrust.TRUSTED

    def __post_init__(self) -> None:
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError("memory importance must be between 0 and 1")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("memory confidence must be between 0 and 1")
        for name in (
            "created_at_ms",
            "observed_at_ms",
            "valid_from_ms",
            "valid_until_ms",
            "retired_at_ms",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be a non-negative UTC epoch milliseconds value")
        if (
            self.valid_from_ms is not None
            and self.valid_until_ms is not None
            and self.valid_until_ms < self.valid_from_ms
        ):
            raise ValueError("valid_until_ms must not precede valid_from_ms")


__all__ = ["MemoryRecord", "MemoryRelationKind", "MemoryTrust"]
