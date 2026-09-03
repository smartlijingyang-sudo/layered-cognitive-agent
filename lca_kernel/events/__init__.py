"""事件机制 —— kernel 元层插件（ADR-0180）。

公开面：
- :class:`EventMechanism` —— 唯一机制入口
- :class:`EventRef` —— 发送返回值
- :class:`Category` / :class:`Plane` / :class:`EventPayload` —— 协议类型
  （实际定义在 :mod:`lca.contracts.event`，本模块 re-export）

不在此暴露：
- :class:`EventRegistry` —— SSOT 加载器，机制内部
- :class:`JournalSink` —— 默认 sink，机制内部
- 任何旧 ``JournalEvent`` / ``record()`` / reflector helper
"""

from lca.contracts.event import (
    Category,
    EventPayload,
    Plane,
    TeamDelegationCacheHit,
    default_plane,
)
from lca_kernel.events.mechanism import EventMechanism, EventRef

__all__ = [
    "Category",
    "EventMechanism",
    "EventPayload",
    "EventRef",
    "Plane",
    "TeamDelegationCacheHit",
    "default_plane",
]
