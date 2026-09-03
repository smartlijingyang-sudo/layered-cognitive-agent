"""事件 payload 重新导出（ADR-0180）。

机制实现引用 :mod:`lca.contracts.event` 中的 payload 类型；本模块做单点 re-export，
便于 plugin manifest 通过 ``lca_kernel.events.payloads.TeamDelegationCacheHit`` 引用，
避免直接 import :mod:`lca.contracts.event`（避免 contracts → lca_kernel 反向）。
"""

from lca.contracts.event import (
    Category,
    EventPayload,
    Plane,
    TeamDelegationCacheHit,
    default_plane,
)

__all__ = [
    "Category",
    "EventPayload",
    "Plane",
    "TeamDelegationCacheHit",
    "default_plane",
]
