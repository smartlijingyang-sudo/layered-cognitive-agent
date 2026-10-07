"""事件总线 —— ADR-0183 §3 / ADR-0184。

公开面：
- :class:`EnvelopeBus` —— 事件总线唯一入口(publish / subscribe / mount_sink /
  register_pipeline)
- :class:`EnvelopeRef` / :class:`EventRef` —— publish 返回值
- :class:`PersistenceObserver` / :class:`EnvelopeDeliveryObserver` —— 落盘 observer
- :class:`SessionEvent` / :class:`SessionObserver` —— Session SSOT 面(ADR-0186)
- :class:`Category` / :class:`Plane` / :class:`EventPayload` —— 协议类型
  （实际定义在 :mod:`lca.contracts.event`，本模块 re-export）

不在此暴露：
- :class:`EventRegistry` —— SSOT 加载器，机制内部
- ``JournalEvent`` / ``record()`` / reflector helper —— 不属于本机制公开面
"""

from pathlib import Path

from lca.contracts.event import (
    Category,
    EventPayload,
    Plane,
    TeamDelegationCacheHit,
    default_plane,
)
from lca.contracts.observability.evidence.fsync import FsyncProtocol
from lca_kernel.events.bus.bus import (
    ConsumerHandle,
    ConsumerResult,
    DeliveryPolicy,
    EnvelopeBus,
    EnvelopeRef,
    EventRef,
)
from lca_kernel.events.fold.fold import (
    EpochHeader,
    StepTree,
    canonicalHeader,
    fold_step_tree,
    foldRequestHeader,
    headerEquals,
)
from lca_kernel.events.persistence.persistence import (
    EnvelopeDeliveryObserver,
    PersistenceFlushTimeoutError,
    PersistenceHealthSnapshot,
    PersistenceObserver,
)
from lca_kernel.events.session.session import (
    SESSION_FORMAT_VERSION,
    SessionEvent,
    SessionHeader,
    SessionObserver,
    SessionProtocol,
    SessionReentryError,
)

_DEFAULT_CONFIG_DIR: Path = Path(__file__).parent / "config"
"""机制 SSOT yaml 目录（ADR-0183 §3.1 / ADR-0180 D2）。"""

__all__ = [
    "SESSION_FORMAT_VERSION",
    "_DEFAULT_CONFIG_DIR",
    "Category",
    "ConsumerHandle",
    "ConsumerResult",
    "DeliveryPolicy",
    "EnvelopeBus",
    "EnvelopeDeliveryObserver",
    "EnvelopeRef",
    "EpochHeader",
    "EventPayload",
    "EventRef",
    "FsyncProtocol",
    "PersistenceFlushTimeoutError",
    "PersistenceHealthSnapshot",
    "PersistenceObserver",
    "Plane",
    "SessionEvent",
    "SessionHeader",
    "SessionObserver",
    "SessionProtocol",
    "SessionReentryError",
    "StepTree",
    "TeamDelegationCacheHit",
    "canonicalHeader",
    "default_plane",
    "foldRequestHeader",
    "fold_step_tree",
    "headerEquals",
]
