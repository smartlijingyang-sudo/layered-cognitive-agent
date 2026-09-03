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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.ids import new_id
from lca_kernel.events.errors import (
    MissingPluginIdentityError,
    UnauthorizedPublishError,
    UnauthorizedSubscribeError,
)
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


# ── 机制本体 ──────────────────────────────────────────────────────────────


_DEFAULT_CONFIG_DIR = Path(__file__).parent / "config"


class EventMechanism:
    """事件机制（kernel 元层，ADR-0180 D1）。"""

    _singleton_instance: EventMechanism | None = None

    def __init__(self, registry: EventRegistry) -> None:
        self._registry = registry
        self._subscribers: dict[Any, list[tuple[type, ConsumerCallback]]] = defaultdict(list)

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
            trace_id="",
            ts=time.time(),
        )
        self._dispatch(payload, ref)
        return ref

    def subscribe(
        self,
        *,
        plugin: type,
        category: Category,
        callback: ConsumerCallback,
    ) -> None:
        """sink / subscriber plugin 唯一订阅入口。

        ``plugin`` 必须是 Python class；机制按 yaml subscribers 解析后的 type 比对。
        """
        if plugin is None or not isinstance(plugin, type):
            raise MissingPluginIdentityError("subscribe")
        if not self._registry.can_subscribe(plugin, category):
            raise UnauthorizedSubscribeError(plugin.__qualname__, category.value)
        self._subscribers[category].append((plugin, callback))

    # ── 内部 ──────────────────────────────────────────────────────────────

    def _dispatch(self, payload: EventPayload, ref: EventRef) -> None:
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
