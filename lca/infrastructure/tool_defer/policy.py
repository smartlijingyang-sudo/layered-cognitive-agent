"""Defer policy: which namespaces stay eager, how the catalog reads (ADR-0256)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

STANDARD_NAMESPACES: tuple[str, ...] = (
    "core",
    "file",
    "shell",
    "memory",
    "skill",
    "web",
    "agent",
    "ext",
)

DEFAULT_NAMESPACE_DESCRIPTIONS: dict[str, str] = {
    "core": "推理原语：按需加载工具目录",
    "file": "文件系统：列出、读取、写入、编辑、移动、搜索文件内容",
    "shell": "执行 shell 命令与脚本；危险操作会先请示你",
    "memory": "搜索与写入长期记忆",
    "skill": "技能的发现、安装与调用",
    "web": "联网搜索与网页抓取",
    "agent": "助理管理、派发子任务、向用户提问",
    "ext": "第三方集成：连接与刷新外部服务",
}

DEFAULT_NAMESPACE_APPROVAL: dict[str, str] = {
    "shell": "require_approval",
}


@dataclass(frozen=True, slots=True)
class DeferPolicy:
    """Run-level switchboard for deferred tool loading."""

    enabled: bool = True
    """False restores legacy behavior: every tool schema, every turn."""

    eager_namespaces: frozenset[str] = frozenset({"core"})
    """Namespaces whose full schemas inject every turn. ``core``
    must stay eager — it holds the tool_search loader itself (Muse L0)."""

    namespace_descriptions: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_NAMESPACE_DESCRIPTIONS)
    )
    """Human-written catalog lines, keyed by namespace. Honest one-liners
    only — a misleading line hides the capability from the model."""

    namespace_approval: Mapping[str, str] = field(
        default_factory=lambda: dict(DEFAULT_NAMESPACE_APPROVAL)
    )
    """Per-namespace approval strategy mapping (e.g. 'shell' -> 'require_approval')."""

    catalog_hint: str = 'call tool_search(namespace="...") to load full schemas'

    discovery_rule: str = (
        "Before concluding a capability is unavailable, check the deferred "
        "namespace catalog above — deferred namespaces load on demand via "
        "tool_search."
    )

    @property
    def known_namespaces(self) -> frozenset[str]:
        return frozenset(self.namespace_descriptions.keys())

    @classmethod
    def default(cls) -> DeferPolicy:
        """The production default: defer everything except core."""
        return cls()


__all__ = [
    "DEFAULT_NAMESPACE_APPROVAL",
    "DEFAULT_NAMESPACE_DESCRIPTIONS",
    "STANDARD_NAMESPACES",
    "DeferPolicy",
]
