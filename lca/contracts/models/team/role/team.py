"""第5.3/5.6节：角色与团队配置契约 + 执行配置契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetryPolicy:
    """工具执行重试策略：指数退避参数 + 可重试错误白名单。"""

    max_retries: int = 3
    backoff_base_s: float = 1.0
    backoff_multiplier: float = 2.0
    retryable_errors: list[str] = field(default_factory=list)


@dataclass
class CacheConfig:
    """工具执行结果缓存配置。"""

    enabled: bool = True
    ttl_s: int = 300
    key_fields: list[str] = field(default_factory=list)


@dataclass
class ToolPermissionManifest:
    """角色级工具权限声明：允许列表 + 调用上限 + 审批清单。"""

    allowed_tools: list[str]
    max_calls_per_task: dict[str, int] = field(default_factory=dict)
    requires_approval: list[str] = field(default_factory=list)

    def add_permitted(self, tool_name: str) -> None:
        """将工具名加入允许列表（幂等）。

        这是 allowed_tools 变更的唯一公共入口；调用方不得直接操作列表。
        """
        if tool_name not in self.allowed_tools:
            self.allowed_tools.append(tool_name)

    def revoke_permitted(self, tool_name: str) -> None:
        """从允许列表移除工具名（幂等）。"""
        self.allowed_tools = [t for t in self.allowed_tools if t != tool_name]


@dataclass
class RoleProfile:
    """Agent 角色画像：goal / backstory / 工具权限 / 语气价值观。"""

    role: str
    goal: str
    backstory: str
    tool_permission_manifest: ToolPermissionManifest
    tone: str | None = None
    values: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
