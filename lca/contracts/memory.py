"""第5.5节：记忆记录契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.contracts.enums import MemoryLayer, MemoryRecordKind


@dataclass
class MemoryRecord:
    """多级记忆记录：支持 working / semantic / episodic / procedural 四种类型。

    ``kind`` 标注语义分类（ADR-0032），``metadata`` 承载归属信息
    （如委派结果的 role / subtask / step）。默认 GENERIC 保持向后兼容。
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
