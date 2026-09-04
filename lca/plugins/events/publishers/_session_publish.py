"""Session-优先 publish helper(PR-3d-sample,ADR-0183 PR-7 后置扩展位)。

publisher 单点入口优先走 active Session.append(为后续 PR 接入
session_service/SessionStore 留 hook 位);无 Session 时 fallback
:func:`lca_kernel.events.bus.EventBus.default().publish`,行为完全等同
于改造前 publisher 直接调 ``EventBus.publish``。

# COMPAT(delete-when: 所有 publisher 完成 Session.append 迁移,
# tracking: ADR-0183 PR-7 + PR-3d 后续批量 PR。fallback 路径在
# rg "EventBus\\.default\\(\\)\\.publish" lca/plugins/events/publishers/ = 0
# 后删除)

设计边界:
- helper 只承载 publisher 入口路由(优先 Session,fallback EventBus);
  payload/producer 字段语义由调用方负责,本模块不重写。
- Session.append 接受 ``payload`` 与 ``producer``;返回 :class:`EventRef`
  以兼容现有 publisher 测试(ref.category / ref.event_id 断言)。
- Session 路径与 EventBus 路径共用同一 ``EventRegistry.can_publish`` 鉴权矩阵
  （S1）;本 helper 在 ``session.append`` 前执行,避免 active Session 时绕过授权。
- ContextVar 隔离:Session 跨 asyncio.Task/copy_context 不串。
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef


def _authorize_producer(payload: Any, producer: Any) -> None:
    """Run EventBus S1 authorization before Session.append.

    Uses the same ``EventBus.default().registry.can_publish`` matrix as
    ``EnvelopeBus.publish``. Raises ``UnauthorizedPublishError`` on deny.
    Missing plugin identity / category defers to EventBus / schema checks.
    """
    from lca_kernel.events.bus import EventBus
    from lca_kernel.events.errors import UnauthorizedPublishError

    bus = EventBus.default()
    coerce = getattr(bus, "_coerce_producer", None)
    producer_cls = coerce(producer) if callable(coerce) else producer
    category = getattr(payload, "category", None)
    if category is None or producer_cls is None:
        return
    registry = bus.registry
    if not registry.can_publish(producer_cls, category):
        identifier = getattr(producer_cls, "__name__", str(producer_cls))
        cat_value = getattr(category, "value", category)
        raise UnauthorizedPublishError(identifier, cat_value)


class _PublishSession(Protocol):
    """publisher 单点 Session 接口(协议形态)。

    实现方可以是 session_service、SessionStore、或后续合入的 Session
    facade;只要提供 ``append(payload, *, producer)`` 即可。

    该 Protocol 是 helper 与 Session 实现方的契约;并非 plugin manifest
    的 capability key——避免与现有 yaml 注册路径重复定义。
    """

    def append(
        self,
        payload: Any,
        *,
        producer: Any,
    ) -> EventRef: ...


_current_session: contextvars.ContextVar[_PublishSession | None] = contextvars.ContextVar(
    "lca_publish_session",
    default=None,
)
"""当前上下文的 active Session(PR-3d-sample 引入)。

wiring 层通过 :func:`set_publish_session` 在 run / request 边界 set,
离开时 reset。EventBus.publish 缺显式 Session 时,本 helper 走 fallback
路径。contextvars 随 asyncio.Task / copy_context 隔离,跨 run 不串。
"""


def set_publish_session(
    session: object | None,
) -> contextvars.Token[_PublishSession | None]:
    """设置当前上下文的 active Session;返回 token 供 reset。

    runtime :class:`~lca.plugins.session.runtime.session.Session` 自动包成
    bus Protocol facade；已是 ``append(payload, *, producer)`` 形态的对象
    原样装载。
    """
    from lca.plugins.session.runtime.bus_facade import as_bus_facade

    return _current_session.set(cast("_PublishSession | None", as_bus_facade(session)))


def reset_publish_session(
    token: contextvars.Token[_PublishSession | None],
) -> None:
    """用 set_publish_session 返回的 token 恢复 active Session。"""
    _current_session.reset(token)


def current_publish_session() -> _PublishSession | None:
    """读当前上下文的 active Session;未设置返回 None。"""
    return _current_session.get()


def publish_via_session(
    payload: Any,
    *,
    producer: Any,
) -> EventRef:
    """优先 Session.append;无 Session 时 fallback EventBus.publish。

    参数:
    - ``payload``:typed 事件 payload(SpineEventPayload 或其它 EventPayload 子类);
      与原 ``EventBus.publish(payload, producer=...)`` 形态一致。
    - ``producer``:publisher plugin class(EventBus 鉴权用)。

    返回:
    :class:`EventRef`。Session 路径返回 ``append`` 回执（runtime Session
    由 bus facade 从 SessionEvent 合成）;EventBus fallback 路径返回真实
    EventRef,与改造前等价。
    """
    session = _current_session.get()
    if session is not None:
        _authorize_producer(payload, producer)
        return session.append(payload, producer=producer)
    from lca_kernel.events.bus import EventBus

    return EventBus.default().publish(payload, producer=producer)


__all__ = [
    "current_publish_session",
    "publish_via_session",
    "reset_publish_session",
    "set_publish_session",
]
