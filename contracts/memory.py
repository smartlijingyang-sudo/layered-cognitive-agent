"""第5.5节：记忆记录契约（含程序性技能与知识图谱三元组）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class MemoryRecord:
    record_id: str
    content: str
    memory_type: Literal["working", "semantic", "episodic", "procedural"]
    importance: float
    recency_score: Optional[float] = None
    embedding: Optional[list[float]] = None
    source_trace_id: Optional[str] = None
    ttl: Optional[int] = None
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
    last_used_at: Optional[datetime] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class KGTriple:
    triple_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_trace_id: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
