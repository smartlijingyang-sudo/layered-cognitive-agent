"""第5.3/5.6节：角色与团队配置契约 + 执行配置契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base_s: float = 1.0
    backoff_multiplier: float = 2.0
    retryable_errors: list[str] = field(default_factory=list)


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl_s: int = 300
    key_fields: list[str] = field(default_factory=list)


@dataclass
class ToolPermissionManifest:
    allowed_tools: list[str]
    max_calls_per_task: dict[str, int] = field(default_factory=dict)
    requires_approval: list[str] = field(default_factory=list)


@dataclass
class RoleProfile:
    role: str
    goal: str
    backstory: str
    tool_permission_manifest: ToolPermissionManifest
    tone: str | None = None
    values: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamConfig:
    process: Literal["hierarchical", "sequential", "parallel", "graph", "debate", "handoff"]
    shared_memory_layers: list[Literal["semantic", "procedural"]] = field(default_factory=list)
    max_rounds: int | None = None
    graph_definition_ref: str | None = None
