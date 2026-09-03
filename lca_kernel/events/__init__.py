"""事件总线 —— ADR-0183 §3 / ADR-0183 PR-7 收口。

公开面：
- :class:`EventBus` —— 唯一机制入口
- :class:`EventRef` —— publish 返回值
- :class:`Category` / :class:`Plane` / :class:`EventPayload` —— 协议类型
  （实际定义在 :mod:`lca.contracts.event`，本模块 re-export）

PR-7 收口：旧 EventMechanism(ADR-0180) 整个文件删除；
producer 入口 = EventBus.publish(payload, *, producer=...)；
consumer 入口 = EventBus.subscribe(*, plugin, category, on_event, failure=...)。

不在此暴露：
- :class:`EventRegistry` —— SSOT 加载器，机制内部
- :class:`JournalSink` —— 默认 sink，机制内部
- 任何旧 ``JournalEvent`` / ``record()`` / reflector helper
"""

from pathlib import Path

from lca.contracts.event import (
    Category,
    EventPayload,
    Plane,
    TeamDelegationCacheHit,
    default_plane,
)
from lca_kernel.events.bus import EventBus, EventRef

_DEFAULT_CONFIG_DIR: Path = Path(__file__).parent / "config"
"""机制 SSOT yaml 目录（ADR-0183 §3.1 / ADR-0180 D2）。"""

__all__ = [
    "_DEFAULT_CONFIG_DIR",
    "Category",
    "EventBus",
    "EventPayload",
    "EventRef",
    "Plane",
    "TeamDelegationCacheHit",
    "default_plane",
]
