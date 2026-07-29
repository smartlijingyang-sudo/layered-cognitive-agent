"""第5.5节：记忆记录契约（含程序性技能与知识图谱三元组）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class MemoryRecord:
    record_id: str
    content: str
    memory_type: Literal["working", "semantic", "episodic", "procedural"]
    importance: float
    recency_score: float | None = None
    embedding: list[float] | None = None
    source_trace_id: str | None = None
    ttl: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillRecord:
    skill_id: str
    name: str
    description: str
    trigger_pattern: str
    workflow_ref: str
    success_rate: float = 0.0
    usage_count: int = 0
    last_used_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class KGTriple:
    triple_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_trace_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
