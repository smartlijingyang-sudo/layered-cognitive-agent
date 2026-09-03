"""事件机制本体 —— ADR-0180 D1/D4。

``EventMechanism`` 是 kernel 元层插件，由 ``lca_kernel`` boot 强制装载。
公开面只暴露 ``send`` 与 ``subscribe`` 两个入口；其他全部 internal。

业务方形态（ADR-0180 C：一切都是插件）：
- 业务方 producer 调 :meth:`EventMechanism.send(payload, *, plugin=MyPluginClass)`
  其中 ``plugin`` 是 Python class（plugin type）；机制按 yaml 中 ``publishers``
  解析后的 type 集合鉴权（必须 class 全路径一致）。
- sink / subscriber plugin 在自己 boot 时调 :meth:`EventMechanism.subscribe(
  plugin=MySubscriberClass, category=..., callback=...)`；机制按 yaml 中
  ``subscribers`` 解析后的 type 集合鉴权。

发送流程：

  plugin == MyClass
      │
      ▼  EventMechanism.send(payload, *, plugin=MyClass)
      │
      ├─ 1. plugin 必填（MissingPluginIdentityError）
      ├─ 2. MyClass ∈ registry.publishers[payload.category]  ← 否则 UnauthorizedPublishError
      ├─ 3. 路由：fanout 到所有该 category 的 subscribers
      │     ├─ 每个 subscriber.callback(payload, ref)    ← 防"偷听"
      └─ 4. 返回 EventRef
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.ids import new_id
from lca_kernel.events.errors import (
    AuthMatrixMismatchError,
    MissingPluginIdentityError,
    UnauthorizedPublishError,
    UnauthorizedSubscribeError,
)
from lca_kernel.events.payloads import EventPluginSpec
from lca_kernel.events.registry import EventRegistry

if TYPE_CHECKING:
    from lca.contracts.event import Category, EventPayload

_log = logging.getLogger(__name__)


# ── 公开类型 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EventRef:
    """机制返回给发送方的轻量引用。"""

    event_id: str
    category: str
    trace_id: str
    ts: float


ConsumerCallback = Callable[["EventPayload", EventRef], None]
# ADR-0181 D6: sink 与 subscriber 性质不同：sink 写盘（fail-fast），subscriber
# 派生（contained）。试点 1 个 SpineChainSink 通过 sinks 注册；0180 业务方
# DelegationCachePlugin 仍走 subscribers 路径，行为不变。
SinkCallback = Callable[["EventPayload", EventRef], None]


# ── 机制本体 ──────────────────────────────────────────────────────────────


_DEFAULT_CONFIG_DIR = Path(__file__).parent / "config"


class EventMechanism:
    """事件机制（kernel 元层，ADR-0180 D1 + ADR-0181 D6）。"""

    _singleton_instance: EventMechanism | None = None

    def __init__(self, registry: EventRegistry) -> None:
        self._registry = registry
        self._subscribers: dict[Any, list[tuple[type, ConsumerCallback]]] = defaultdict(list)
        # ADR-0181 D6: sinks 落盘路径，FD-1 fail-fast（首个 sink 抛错上抛 sender）。
        self._sinks: dict[Any, list[tuple[type, SinkCallback]]] = defaultdict(list)

    # ── 进程级单例 ────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> EventMechanism:
        if cls._singleton_instance is None:
            cls._singleton_instance = cls(EventRegistry.load(_DEFAULT_CONFIG_DIR))
        return cls._singleton_instance

    @classmethod
    def set_default(cls, instance: EventMechanism | None) -> None:
        cls._singleton_instance = instance

    @classmethod
    def reset_singleton(cls) -> None:
        cls._singleton_instance = None

    # ── 公开面（ADR-0180 D4）───────────────────────────────────────────────

    def send(self, payload: EventPayload, *, plugin: type) -> EventRef:
        """业务方唯一发送入口。

        ``plugin`` 必须是 Python class；机制按 yaml publishers 解析后的 type 比对。
        """
        if plugin is None or not isinstance(plugin, type):
            raise MissingPluginIdentityError("send")
        category = payload.category
        if not self._registry.can_publish(plugin, category):
            raise UnauthorizedPublishError(plugin.__qualname__, category.value)
        ref = EventRef(
            event_id=new_id("evt"),
            category=category.value,
            trace_id=self._resolve_trace_id(payload),
            ts=time.time(),
        )
        # ADR-0181 D6: FD-1 sink fail-fast（先），FD-2 subscriber contained（后）。
        self._dispatch_sinks(payload, ref)
        self._dispatch_subscribers(payload, ref)
        return ref

    def subscribe(
        self,
        *,
        plugin: type,
        category: Category,
        callback: ConsumerCallback,
    ) -> None:
        """subscriber plugin 唯一订阅入口（派生型，FD-2 contained）。

        ``plugin`` 必须是 Python class；机制按 yaml subscribers 解析后的 type 比对。
        """
        if plugin is None or not isinstance(plugin, type):
            raise MissingPluginIdentityError("subscribe")
        if not self._registry.can_subscribe(plugin, category):
            raise UnauthorizedSubscribeError(plugin.__qualname__, category.value)
        self._subscribers[category].append((plugin, callback))

    def register_sink(
        self,
        *,
        plugin: type,
        category: Category,
        callback: SinkCallback,
    ) -> None:
        """sink plugin 唯一注册入口（落盘型，FD-1 fail-fast）。

        ``plugin`` 必须是 Python class；机制按 yaml subscribers 解析后的 type 比对
        （sink 复用 subscribers 白名单，因 sink 是 subscriber 的子集）。
        """
        if plugin is None or not isinstance(plugin, type):
            raise MissingPluginIdentityError("register_sink")
        if not self._registry.can_subscribe(plugin, category):
            raise UnauthorizedSubscribeError(plugin.__qualname__, category.value)
        self._sinks[category].append((plugin, callback))

    # ── boot-time 鉴权矩阵互校验（ADR-0180 D3）─────────────────────────────

    def validate_auth_matrix(
        self,
        plugin_specs: Iterable[EventPluginSpec],
    ) -> None:
        """业务方 plugin 鉴权声明 vs yaml SSOT 互校验。

        对每个 :class:`EventPluginSpec`：
        - ``plugin_id`` 是 plugin class 全路径（与 yaml publishers/subscribers
          解析后的 class 全路径对齐；不接短 plugin_id 字符串）。
        - ``event_publishes`` 内每个 category 必须在 yaml publishers 白名单中
          存在（即本 plugin class 已被 yaml 授权 publish 该 category）。
        - ``event_subscribes`` 内每个 category 必须在 yaml subscribers 白名单
          中存在。

        任何不匹配 → :class:`AuthMatrixMismatchError`，机制 boot 失败。

        调用点：profile boot 完成后、plugins 装载前；本方法由 profile loader
        触发（`lca_kernel/events/manifest.py` 当前未挂 profile 钩子；后续 PR
        接 profile integration 时启用）。
        """
        for spec in plugin_specs:
            missing_publish = sorted(
                c.value
                for c in spec.event_publishes
                if spec.plugin_id
                not in {
                    f"{cls.__module__}.{cls.__qualname__}"
                    for cls in self._registry.publishers.get(c, frozenset())
                }
            )
            missing_subscribe = sorted(
                c.value
                for c in spec.event_subscribes
                if spec.plugin_id
                not in {
                    f"{cls.__module__}.{cls.__qualname__}"
                    for cls in self._registry.subscribers.get(c, frozenset())
                }
            )
            if missing_publish or missing_subscribe:
                raise AuthMatrixMismatchError(
                    spec.plugin_id,
                    missing_publish=set(missing_publish),
                    missing_subscribe=set(missing_subscribe),
                )

    # ── 内部（ADR-0181 D6 FD-1 / FD-2）────────────────────────────────────

    @staticmethod
    def _resolve_trace_id(payload: EventPayload) -> str:
        """trace_id 解析:payload.trace_id → ambient contextvars → new_id。

        与 EventBus._resolve_trace_id 同一解析链(ADR-0183 §3.9)。
        bus 模块级 import mechanism,故此处函数内延迟 import 防循环。
        """
        from lca_kernel.events.bus import _current_trace_id

        return getattr(payload, "trace_id", None) or _current_trace_id.get() or new_id("trc")

    def _dispatch_sinks(self, payload: EventPayload, ref: EventRef) -> None:
        """FD-1: 首个 sink 抛错 → 上抛 sender（fail-fast）。"""
        category = payload.category
        for _plugin_cls, callback in self._sinks.get(category, ()):
            callback(payload, ref)  # 不 try/except；sink 失败即上抛

    def _dispatch_subscribers(self, payload: EventPayload, ref: EventRef) -> None:
        """FD-2: subscriber 抛错 → contained，原事件仍落盘。"""
        category = payload.category
        for _plugin_cls, callback in self._subscribers.get(category, ()):
            try:
                callback(payload, ref)
            except Exception:
                _log.exception(
                    "consumer callback failed",
                    extra={"event_id": ref.event_id, "category": category.value},
                )

    # ── 自检 ──────────────────────────────────────────────────────────────

    @property
    def registry(self) -> EventRegistry:
        return self._registry


__all__ = ["ConsumerCallback", "EventMechanism", "EventRef"]
