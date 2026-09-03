"""事件 payload 重新导出（ADR-0180 / ADR-0181）。

机制实现引用 :mod:`lca.contracts.event` 中的 payload 类型；本模块做单点 re-export，
便于 plugin manifest 通过 ``lca_kernel.events.payloads.TeamDelegationCacheHit`` 引用，
避免直接 import :mod:`lca.contracts.event`（避免 contracts → lca_kernel 反向）。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from lca.contracts.event import (
    Category,
    EventPayload,
    Plane,
    TeamDelegationCacheHit,
    default_plane,
)
from lca_kernel.events.payloads_spine import (
    SPINE_EXECUTION_POINTS,
    SpineEventPayload,
)


@dataclass(frozen=True, slots=True)
class EventPluginSpec:
    """业务方 events plugin 的鉴权声明（ADR-0180 D3）。

    每个 events plugin manifest 必须声明：
    - ``plugin_id`` — **plugin class 全路径**（如
      ``lca.plugins.events.publishers.delegation_cache.plugin.DelegationCachePlugin``）；
      与 yaml publishers / subscribers 解析后的 class 全路径对齐。短
      plugin_id 字符串（如 ``delegation_cache``）不被机制识别。
    - ``event_publishes`` — 本 plugin 计划 publish 的 category 集合
    - ``event_subscribes`` — 本 plugin 计划 subscribe 的 category 集合

    ``EventMechanism.validate_auth_matrix()`` 在 boot 时遍历该集合，逐 plugin 比对：
    - 集合内每个 category 必须在 yaml publishers / subscribers 白名单中存在
    - 反向：yaml 列为 X 但本 plugin 未声明的 category → 抛 AuthMatrixMismatchError

    该类型替代旧 `plugin_spec: dict[str, Any]` 裸 dict 形式；旧 dict 形式不被机制
    识别，mechanism 只接受 EventPluginSpec 输入。
    """

    plugin_id: str
    event_publishes: frozenset[Category] = field(default_factory=frozenset)
    event_subscribes: frozenset[Category] = field(default_factory=frozenset)

    def to_dict(self) -> Mapping[str, object]:
        """转 dict 形态（用于旧测试断言兼容 + 文档展示）。"""
        return {
            "plugin_id": self.plugin_id,
            "event_publishes": [c.value for c in self.event_publishes],
            "event_subscribes": [c.value for c in self.event_subscribes],
        }


__all__ = [
    "SPINE_EXECUTION_POINTS",
    "Category",
    "EventPayload",
    "EventPluginSpec",
    "Plane",
    "SpineEventPayload",
    "TeamDelegationCacheHit",
    "default_plane",
]
