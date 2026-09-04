"""事件总线 —— ADR-0183 §3 / ADR-0183 PR-7 收口 / ADR-0184 PR-1。

公开面：
- :class:`EnvelopeBus` —— ADR-0184 PR-1 统一入口(主)
- :class:`EventBus` —— EnvelopeBus 兼容 shim(30 天窗口)
- :class:`EnvelopeRef` / :class:`EventRef` —— publish 返回值
- :class:`PersistenceObserver` / :class:`EnvelopeDeliveryObserver` —— 落盘 observer
- :class:`SessionEvent` / :class:`SessionObserver` —— Session SSOT 面(ADR-0186)
- :class:`Category` / :class:`Plane` / :class:`EventPayload` —— 协议类型
  （实际定义在 :mod:`lca.contracts.event`，本模块 re-export）

PR-7 收口：旧 EventMechanism(ADR-0180) 整个文件删除；
PR-1 收口：EventBus 改为 EnvelopeBus 子类,保留全部现有方法。

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
from lca_kernel.events.bus import (
    ConsumerHandle,
    ConsumerResult,
    DeliveryPolicy,
    EnvelopeBus,
    EnvelopeRef,
    EventBus,
    EventRef,
)
from lca_kernel.events.fold import (
    EpochHeader,
    StepTree,
    canonicalHeader,
    fold_step_tree,
    foldRequestHeader,
    headerEquals,
)
from lca_kernel.events.persistence import (
    EnvelopeDeliveryObserver,
    FsyncPolicy,
    PersistenceFlushTimeout,
    PersistenceHealthSnapshot,
    PersistenceObserver,
)
from lca_kernel.events.session import (
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
    "EventBus",
    "EventPayload",
    "EventRef",
    "FsyncPolicy",
    "PersistenceFlushTimeout",
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
