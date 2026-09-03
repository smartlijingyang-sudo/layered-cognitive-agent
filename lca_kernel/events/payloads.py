"""事件 payload 重新导出（ADR-0180 / ADR-0181 / ADR-0183 PR-7）。

EventBus.publish payload 引用 :mod:`lca.contracts.event` 中的 payload 类型；本模块做单点 re-export，
便于 plugin manifest 通过 ``lca_kernel.events.payloads.TeamDelegationCacheHit`` 引用，
避免直接 import :mod:`lca.contracts.event`（避免 contracts → lca_kernel 反向）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import model_validator

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

    ``EventBus.subscribe(*, plugin, ...)`` 鉴权用 yaml subscribers 白名单；
    EventMechanism.validate_auth_matrix() 已删除，鉴权在 registry.can_subscribe
    一次性物化进 ``subscribers`` 映射。
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


# ── 机制自观察（ADR-0183 §3.10）─────────────────────────────────────────

DISPATCH_SELF_OBSERVATION_CATEGORIES: frozenset[str] = frozenset(
    {"event.bus.dispatch.sinks.end", "event.bus.dispatch.consumers.end"}
)
"""机制自观察事件字符串闭集（ADR-0183 §3.10）。

不在 :class:`Category` 枚举内：扩 Category 闭集需 ADR + yaml SSOT 登记，
自观察是框架内部事件，走 EventBus 内部路径，不进注册表鉴权矩阵。
I-FW-BUS-4：业务方不得订阅本组事件。
"""


class MechanismDispatchEventPayload(EventPayload):
    """机制自观察事件：一次 dispatch 的阶段完成（ADR-0183 §3.10）。

    ``category`` 覆盖父类 Category 枚举，取字符串闭集
    （见 :data:`DISPATCH_SELF_OBSERVATION_CATEGORIES`）——闭集约束见该常量
    docstring。本 payload 只能经 :meth:`EventBus._emit_self_observation`
    内部路径流转：不进注册表鉴权、不触发 post_dispatch hook（防递归）。

    字段契约：
    - ``consumer_count`` — 本阶段执行的 consumer 数
    - ``duration_s`` — 自被观察事件 publish 起至 post_dispatch 的墙钟秒数
    - ``contained_failures`` — contained 路径失败异常类名（sinks 阶段恒为空：
      sink 失败走 fail-fast 上抛，post_dispatch 不会执行）
    """

    # 字符串闭集(见 DISPATCH_SELF_OBSERVATION_CATEGORIES)。父类 category 是
    # Category 枚举闭集,扩枚举需 ADR;自观察事件不进业务闭集,故此处放宽为
    # str,由 _validate_dispatch_fields 守住闭集。
    category: str  # type: ignore[assignment]
    consumer_count: int
    duration_s: float
    contained_failures: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_dispatch_fields(self) -> MechanismDispatchEventPayload:
        if self.category not in DISPATCH_SELF_OBSERVATION_CATEGORIES:
            raise ValueError(
                f"MechanismDispatchEventPayload.category 必须在闭集 "
                f"{sorted(DISPATCH_SELF_OBSERVATION_CATEGORIES)} 内，"
                f"got {self.category!r}"
            )
        if self.consumer_count < 0:
            raise ValueError(f"consumer_count must be >= 0, got {self.consumer_count}")
        if self.duration_s < 0:
            raise ValueError(f"duration_s must be >= 0, got {self.duration_s}")
        return self


__all__ = [
    "DISPATCH_SELF_OBSERVATION_CATEGORIES",
    "SPINE_EXECUTION_POINTS",
    "Category",
    "EventPayload",
    "EventPluginSpec",
    "MechanismDispatchEventPayload",
    "Plane",
    "SpineEventPayload",
    "TeamDelegationCacheHit",
    "default_plane",
]
