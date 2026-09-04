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
- helper **不**做鉴权 / schema 校验:鉴权仍由 EventBus 入口在 fallback
  路径执行;Session 路径由 Session.append 内部负责。
- ContextVar 隔离:Session 跨 asyncio.Task/copy_context 不串。
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, Protocol

from lca.contracts.atoms.ids import new_id

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef


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
    session: _PublishSession | None,
) -> contextvars.Token[_PublishSession | None]:
    """设置当前上下文的 active Session;返回 token 供 reset。"""
    return _current_session.set(session)


def reset_publish_session(
    token: contextvars.Token[_PublishSession | None],
) -> None:
    """用 set_publish_session 返回的 token 恢复 active Session。"""
    _current_session.reset(token)


def current_publish_session() -> _PublishSession | None:
    """读当前上下文的 active Session;未设置返回 None。"""
    return _current_session.get()


def _synthetic_ref(payload: Any) -> EventRef:
    """Session.append 返回路径合成的 EventRef(用于 fallback 兼容)。

    Session 路径暂未绑定 EventBus,需构造一个最小 EventRef 满足现有
    publisher 测试断言(ref.category / ref.event_id)。
    """
    from lca_kernel.events.bus import EventRef

    category = getattr(payload, "category", None)
    cat_str = getattr(category, "value", None) or str(category or "")
    return EventRef(
        event_id=new_id("evt"),
        category=cat_str,
        trace_id="",
        ts=0.0,
        persisted=False,
        subscriber_count=0,
    )


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
    :class:`EventRef`。Session 路径返回合成的最小 EventRef(后续 PR 接入
    session_service 后会换成 SessionEvent 与 EventRef 的映射);EventBus
    fallback 路径返回真实 EventRef,与改造前等价。
    """
    session = _current_session.get()
    if session is not None:
        return session.append(payload, producer=producer)
    from lca_kernel.events.bus import EventBus

    return EventBus.default().publish(payload, producer=producer)


__all__ = [
    "current_publish_session",
    "publish_via_session",
    "reset_publish_session",
    "set_publish_session",
]
