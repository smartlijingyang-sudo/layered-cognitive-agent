"""Defer policy: which namespaces stay eager, how the catalog reads (ADR-0256)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from lca.contracts.models.vocal.models import VocalMode

STANDARD_NAMESPACES: tuple[str, ...] = (
    "core",
    "file",
    "shell",
    "memory",
    "skill",
    "web",
    "agent",
    "ext",
    # ADR-0268 §4：新增 lca（运行时控制）与 cron（定时任务）两个域。
    "lca",
    "cron",
    # ADR-0269 §4：新增 avatar（头像生成与换装）工具域。
    "avatar",
)

DEFAULT_NAMESPACE_DESCRIPTIONS: dict[str, str] = {
    "core": "推理原语：按需加载工具目录",
    "file": "文件系统（写操作）：写入、编辑、移动文件",
    "shell": "执行 shell 命令与脚本；危险操作会先请示你",
    "memory": "搜索与写入长期记忆",
    "skill": "技能的发现、安装与调用",
    "web": "联网搜索与网页抓取",
    "agent": "助理管理、派发子任务、向用户提问",
    "ext": "第三方集成：连接与刷新外部服务",
    "lca": "运行时控制：handoff 轮静默结束",
    "cron": "定时任务：创建、查看、更新、删除与即将到来列表",
    "avatar": "头像生成与换装：创建候选、激活、查询、清除与定时换装",
}

DEFAULT_NAMESPACE_APPROVAL: dict[str, str] = {
    "shell": "require_approval",
}


@dataclass(frozen=True, slots=True)
class DeferPolicy:
    """Run-level switchboard for deferred tool loading."""

    enabled: bool = True
    """False restores legacy behavior: every tool schema, every turn."""

    eager_namespaces: frozenset[str] = frozenset({"core", "memory"})
    """Namespaces whose full schemas inject every turn. ``core``
    must stay eager — it holds the tool_search loader itself (Muse L0).
    ``memory`` must stay eager — aligns with ADR-0260 mandatory retrieval
    duty and write-before-claim contract so memory tools are immediately
    available without a separate tool_search roundtrip."""

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
        return frozenset(self.namespace_descriptions)

    @classmethod
    def default(cls) -> DeferPolicy:
        """The production default: defer everything except core."""
        return cls()

    @classmethod
    def for_vocal_mode(cls, vocal_mode: str) -> DeferPolicy:
        """Per-run policy for a vocal mode; gated keeps ``agent`` eager.

        The gated vocal contract makes ``send_message`` the assistant's only
        channel to the user (ADR-0248), so the ``agent`` namespace that
        carries it must be visible on the first turn. Leaving it deferred
        made the model call a tool whose schema was never loaded, spinning
        the act→think re-ask loop until LoopObligationExceededError
        (run_f70ccf932e9d).
        """
        policy = cls.default()
        if str(vocal_mode or "") == VocalMode.GATED.value:
            return replace(
                policy,
                eager_namespaces=policy.eager_namespaces | {"agent"},
            )
        return policy


__all__ = [
    "DEFAULT_NAMESPACE_APPROVAL",
    "DEFAULT_NAMESPACE_DESCRIPTIONS",
    "STANDARD_NAMESPACES",
    "DeferPolicy",
]
