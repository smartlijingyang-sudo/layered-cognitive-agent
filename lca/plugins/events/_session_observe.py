"""Session.observe 注册接缝 —— 事件 consumer plugin 迁移模式样本（PR-3f-sample）。

事件 consumer plugin（sinks / subscribers）优先把事件 callback 注册到
Session 观察面（:meth:`SessionObserverTarget.observe`）；Session 未装载时
调用方回退 ``EventBus.mount_sink`` / ``subscribe``，wire 行为与 bus 直挂
形态一致。

所有权：进程级当前 Session 观察目标的本模块槽位 ``_current_session`` 是
唯一真值；机制方（per-run Session owner）在 Session 构造时经
:func:`set_session` 装载、teardown 时清空。本接缝只做注册路由，不做
鉴权与落盘 —— 事件派发语义由 Session 机制定义。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from lca.contracts.event import EventPayload
from lca_kernel.events import EventRef

__all__ = [
    "EventObserverCallback",
    "SessionObserverTarget",
    "current_session",
    "register_as_session_observer",
    "set_session",
]

EventObserverCallback = Callable[[EventPayload, EventRef], None]
"""观察者回调签名 —— 与 ``EventBus.subscribe`` 的 ``on_event`` 契约同源。"""


@runtime_checkable
class SessionObserverTarget(Protocol):
    """Session 机制提供的观察面接缝。

    ``observe`` 把 ``callback`` 以 ``plugin`` 名义注册；派发时序、失败
    语义与注销由 Session 机制定义，本 Protocol 只约束注册入口形状。
    """

    def observe(self, plugin: type, callback: EventObserverCallback) -> object: ...


_current_session: SessionObserverTarget | None = None


def set_session(session: object | None) -> None:
    """装载 / 清空进程级 Session 观察目标。

    所有权：机制方（per-run Session owner）是唯一调用方 —— Session 构造
    时装载，teardown 时传 ``None`` 清空。传入不带 ``observe`` 的对象抛
    :class:`TypeError`（fail-loud，禁止静默降级成无观察态）。
    runtime :class:`~lca.plugins.session.runtime.session.Session` 自动包成
    bus Protocol facade（``observe(plugin, callback)``）；已是该形态的对象
    原样装载。
    """
    global _current_session
    if session is None:
        _current_session = None
        return
    from lca.plugins.session.runtime.bus_facade import as_bus_facade

    bound = as_bus_facade(session)
    if not isinstance(bound, SessionObserverTarget):
        msg = f"Session 观察目标必须提供 observe()；got {type(session).__name__}"
        raise TypeError(msg)
    _current_session = bound


def current_session() -> SessionObserverTarget | None:
    """读进程级 Session 观察目标；未装载返回 ``None``。"""
    return _current_session


def register_as_session_observer(plugin: type, callback: EventObserverCallback) -> bool:
    """优先经 Session.observe 注册事件观察者。

    返回 ``True`` = Session 已装载且 ``observe`` 正常返回，注册完成；
    返回 ``False`` = Session 未装载，调用方必须回退
    ``EventBus.mount_sink`` / ``subscribe``。Session 已装载但 ``observe``
    抛错时上抛 —— 机制在场却损坏是真实故障（fail-loud）；缺席是唯一
    合法的回退触发条件。

    precondition：``plugin`` 是 plugin marker class（与
    ``EventBus.subscribe`` 的 ``plugin=`` 实参同源）；``callback`` 符合
    :data:`EventObserverCallback` 签名。
    """
    session = _current_session
    if session is None:
        return False
    session.observe(plugin, callback)
    return True
